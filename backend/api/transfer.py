from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
from datetime import datetime
from ..db import get_db
from ..models.user import User, UserRole
from ..models.evidence import Evidence
from ..models.transfer import Transfer, Custody, TransferStatus
from ..models.audit import AuditLog
from ..schemas.transfer import TransferRequest, TransferResponse
from ..api.auth import get_current_user
from ..core.audit import create_audit_entry

router = APIRouter()


def can_request_transfer(user: User, custody: Custody) -> bool:
    """Check if user can request transfer (must be current custodian)"""
    return custody.current_user_id == user.id


def can_accept_transfer(user: User, transfer: Transfer) -> bool:
    """Check if user can accept transfer (must be the recipient)"""
    return transfer.to_user_id == user.id


@router.post("/request", response_model=TransferResponse)
def request_transfer(
    transfer_data: TransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request evidence transfer (current custodian only)"""
    # Verify evidence exists
    evidence = db.query(Evidence).filter(Evidence.id == transfer_data.evidence_id).first()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Get current custody
    custody = db.query(Custody).filter(Custody.evidence_id == transfer_data.evidence_id).first()
    if not custody:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No custody record found for evidence"
        )
    
    # Check permissions
    if not can_request_transfer(current_user, custody):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only current custodian can request transfer"
        )
    
    # Verify recipient exists
    recipient = db.query(User).filter(User.id == transfer_data.to_user_id).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient user not found"
        )
    
    # Check for existing pending transfer
    existing_transfer = db.query(Transfer).filter(
        Transfer.evidence_id == transfer_data.evidence_id,
        Transfer.status == TransferStatus.PENDING
    ).first()
    if existing_transfer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pending transfer already exists for this evidence"
        )
    
    # Create transfer request
    transfer = Transfer(
        evidence_id=transfer_data.evidence_id,
        from_user_id=current_user.id,
        to_user_id=transfer_data.to_user_id,
        reason=transfer_data.reason,
        status=TransferStatus.PENDING
    )
    
    db.add(transfer)
    db.flush()  # Get ID without committing
    
    # Create audit log
    audit_details = {
        "action": "TRANSFER_REQUESTED",
        "transfer_id": transfer.id,
        "from_user": current_user.name,
        "to_user": recipient.name,
        "reason": transfer_data.reason
    }
    
    # Get previous hash for audit chain
    prev_audit = db.query(AuditLog).filter(
        AuditLog.evidence_id == transfer_data.evidence_id
    ).order_by(AuditLog.id.desc()).first()
    
    prev_hash = prev_audit.entry_hash_hex if prev_audit else ""
    
    audit_entry = create_audit_entry(
        evidence_id=transfer_data.evidence_id,
        actor_user_id=current_user.id,
        action="TRANSFER_REQUESTED",
        details=audit_details,
        prev_hash=prev_hash
    )
    
    audit_log = AuditLog(
        evidence_id=transfer_data.evidence_id,
        actor_user_id=current_user.id,
        action=audit_entry["action"],
        details_json=json.dumps(audit_entry["details"]),
        ts_utc=datetime.fromisoformat(audit_entry["ts_utc"]),
        prev_hash_hex=audit_entry["prev_hash_hex"],
        entry_hash_hex=audit_entry["entry_hash_hex"]
    )
    db.add(audit_log)
    
    db.commit()
    db.refresh(transfer)
    
    # Prepare response
    response = TransferResponse.from_orm(transfer)
    response.from_user_name = current_user.name
    response.to_user_name = recipient.name
    response.evidence_id_str = evidence.evidence_id_str
    
    return response


@router.post("/accept/{transfer_id}", response_model=TransferResponse)
def accept_transfer(
    transfer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept pending transfer (recipient only)"""
    # Get transfer
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    # Check permissions
    if not can_accept_transfer(current_user, transfer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the recipient can accept this transfer"
        )
    
    # Check transfer status
    if transfer.status != TransferStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transfer is not pending (status: {transfer.status.value})"
        )
    
    # Get evidence and users for audit
    evidence = db.query(Evidence).filter(Evidence.id == transfer.evidence_id).first()
    from_user = db.query(User).filter(User.id == transfer.from_user_id).first()
    
    # Update transfer status
    transfer.status = TransferStatus.ACCEPTED
    transfer.accepted_at_utc = datetime.utcnow()
    
    # Update custody
    custody = db.query(Custody).filter(Custody.evidence_id == transfer.evidence_id).first()
    if custody:
        custody.current_user_id = current_user.id
        custody.since_utc = datetime.utcnow()
    else:
        # Create new custody record if none exists
        custody = Custody(
            evidence_id=transfer.evidence_id,
            current_user_id=current_user.id
        )
        db.add(custody)
    
    # Create audit log
    audit_details = {
        "action": "TRANSFER_ACCEPTED",
        "transfer_id": transfer.id,
        "from_user": from_user.name if from_user else "Unknown",
        "to_user": current_user.name,
        "reason": transfer.reason
    }
    
    # Get previous hash for audit chain
    prev_audit = db.query(AuditLog).filter(
        AuditLog.evidence_id == transfer.evidence_id
    ).order_by(AuditLog.id.desc()).first()
    
    prev_hash = prev_audit.entry_hash_hex if prev_audit else ""
    
    audit_entry = create_audit_entry(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action="TRANSFER_ACCEPTED",
        details=audit_details,
        prev_hash=prev_hash
    )
    
    audit_log = AuditLog(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action=audit_entry["action"],
        details_json=json.dumps(audit_entry["details"]),
        ts_utc=datetime.fromisoformat(audit_entry["ts_utc"]),
        prev_hash_hex=audit_entry["prev_hash_hex"],
        entry_hash_hex=audit_entry["entry_hash_hex"]
    )
    db.add(audit_log)
    
    db.commit()
    db.refresh(transfer)
    
    # Prepare response
    response = TransferResponse.from_orm(transfer)
    response.from_user_name = from_user.name if from_user else "Unknown"
    response.to_user_name = current_user.name
    response.evidence_id_str = evidence.evidence_id_str if evidence else None
    
    return response


@router.get("/pending", response_model=List[TransferResponse])
def get_pending_transfers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending transfers for current user"""
    transfers = db.query(Transfer).filter(
        Transfer.to_user_id == current_user.id,
        Transfer.status == TransferStatus.PENDING
    ).all()
    
    # Add user and evidence info
    response_list = []
    for transfer in transfers:
        from_user = db.query(User).filter(User.id == transfer.from_user_id).first()
        evidence = db.query(Evidence).filter(Evidence.id == transfer.evidence_id).first()
        
        response = TransferResponse.from_orm(transfer)
        response.from_user_name = from_user.name if from_user else "Unknown"
        response.to_user_name = current_user.name
        response.evidence_id_str = evidence.evidence_id_str if evidence else None
        
        response_list.append(response)
    
    return response_list


@router.get("/pending-outgoing", response_model=List[TransferResponse])
def get_my_outgoing_pending_transfers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get transfers that I initiated and are still pending (I am current custodian)."""
    transfers = db.query(Transfer).filter(
        Transfer.from_user_id == current_user.id,
        Transfer.status == TransferStatus.PENDING
    ).all()

    response_list = []
    for transfer in transfers:
        to_user = db.query(User).filter(User.id == transfer.to_user_id).first()
        evidence = db.query(Evidence).filter(Evidence.id == transfer.evidence_id).first()

        response = TransferResponse.from_orm(transfer)
        response.from_user_name = current_user.name
        response.to_user_name = to_user.name if to_user else "Unknown"
        response.evidence_id_str = evidence.evidence_id_str if evidence else None
        response_list.append(response)

    return response_list


@router.post("/cancel/{transfer_id}", response_model=TransferResponse)
def cancel_transfer(
    transfer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a pending transfer by the initiator (from_user)."""
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")

    # Only initiator can cancel
    if transfer.from_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the initiator can cancel this transfer")

    if transfer.status != TransferStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Transfer is not pending (status: {transfer.status.value})")

    # Update status
    transfer.status = TransferStatus.CANCELLED

    # Audit
    to_user = db.query(User).filter(User.id == transfer.to_user_id).first()
    evidence = db.query(Evidence).filter(Evidence.id == transfer.evidence_id).first()
    details = {
        "action": "TRANSFER_CANCELLED",
        "transfer_id": transfer.id,
        "from_user": current_user.name,
        "to_user": to_user.name if to_user else "Unknown",
        "reason": transfer.reason,
    }
    prev = db.query(AuditLog).filter(AuditLog.evidence_id == transfer.evidence_id).order_by(AuditLog.id.desc()).first()
    prev_hash = prev.entry_hash_hex if prev else ""
    entry = create_audit_entry(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action="TRANSFER_CANCELLED",
        details=details,
        prev_hash=prev_hash,
    )
    audit_log = AuditLog(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action=entry["action"],
        details_json=json.dumps(entry["details"]),
        ts_utc=datetime.fromisoformat(entry["ts_utc"]),
        prev_hash_hex=entry["prev_hash_hex"],
        entry_hash_hex=entry["entry_hash_hex"],
    )
    db.add(audit_log)

    db.commit()
    db.refresh(transfer)

    response = TransferResponse.from_orm(transfer)
    response.from_user_name = current_user.name
    response.to_user_name = to_user.name if to_user else "Unknown"
    response.evidence_id_str = evidence.evidence_id_str if evidence else None
    return response

@router.post("/reject/{transfer_id}", response_model=TransferResponse)
def reject_transfer(
    transfer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reject pending transfer (recipient only). Marks as CANCELLED and logs audit."""
    # Get transfer
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    # Check permissions
    if not can_accept_transfer(current_user, transfer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the recipient can reject this transfer"
        )
    
    # Check transfer status
    if transfer.status != TransferStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transfer is not pending (status: {transfer.status.value})"
        )
    
    # Get users and evidence for audit
    from_user = db.query(User).filter(User.id == transfer.from_user_id).first()
    evidence = db.query(Evidence).filter(Evidence.id == transfer.evidence_id).first()
    
    # Update transfer status
    transfer.status = TransferStatus.CANCELLED
    
    # Create audit log
    audit_details = {
        "action": "TRANSFER_REJECTED",
        "transfer_id": transfer.id,
        "from_user": from_user.name if from_user else "Unknown",
        "to_user": current_user.name,
        "reason": transfer.reason
    }
    prev_audit = db.query(AuditLog).filter(
        AuditLog.evidence_id == transfer.evidence_id
    ).order_by(AuditLog.id.desc()).first()
    prev_hash = prev_audit.entry_hash_hex if prev_audit else ""
    audit_entry = create_audit_entry(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action="TRANSFER_REJECTED",
        details=audit_details,
        prev_hash=prev_hash
    )
    audit_log = AuditLog(
        evidence_id=transfer.evidence_id,
        actor_user_id=current_user.id,
        action=audit_entry["action"],
        details_json=json.dumps(audit_entry["details"]),
        ts_utc=datetime.fromisoformat(audit_entry["ts_utc"]),
        prev_hash_hex=audit_entry["prev_hash_hex"],
        entry_hash_hex=audit_entry["entry_hash_hex"]
    )
    db.add(audit_log)
    
    db.commit()
    db.refresh(transfer)
    
    # Prepare response
    response = TransferResponse.from_orm(transfer)
    response.from_user_name = from_user.name if from_user else "Unknown"
    response.to_user_name = current_user.name
    response.evidence_id_str = evidence.evidence_id_str if evidence else None
    return response
