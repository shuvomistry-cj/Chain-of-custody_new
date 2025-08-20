from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
import io
from ..db import get_db
from ..models.user import User, UserRole
from ..models.evidence import Evidence, EvidenceFile
from ..models.transfer import Custody
from ..models.audit import AuditLog
from ..schemas.evidence import EvidenceResponse, EvidenceListResponse
from ..api.auth import get_current_user
from ..core.config import settings
from ..core.crypto import encrypt_file_data, decrypt_file_data, compute_sha256
from ..core.audit import create_audit_entry

router = APIRouter()


def can_create_evidence(user: User) -> bool:
    """Check if user can create evidence"""
    return user.role in [UserRole.COLLECTOR, UserRole.ANALYST, UserRole.ADMIN]


def can_view_evidence(user: User, evidence: Evidence, custody: Optional[Custody] = None) -> bool:
    """Check if user can view evidence.
    - AUDITOR: full read access
    - Others (including ADMIN): only if current custodian or creator
    """
    if user.role == UserRole.AUDITOR:
        return True
    if custody and custody.current_user_id == user.id:
        return True
    if evidence.collected_by_user_id == user.id:
        return True
    return False


def can_download_files(user: User, custody: Optional[Custody] = None) -> bool:
    """Check if user can download evidence files (only current custodian)"""
    return custody and custody.current_user_id == user.id


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file"""
    if file.content_type not in settings.allowed_mime_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed"
        )
    
    if file.size and file.size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum of {settings.max_file_size} bytes"
        )


@router.post("/", response_model=EvidenceResponse)
async def create_evidence(
    agency: str = Form(...),
    case_no: str = Form(...),
    offense: str = Form(...),
    item_no: str = Form(...),
    badge_no: str = Form(...),
    location: str = Form(...),
    collected_at: str = Form(...),
    description: str = Form(...),
    evidence_name: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new evidence with file uploads"""
    # Validate permissions
    if not can_create_evidence(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only COLLECTOR, ANALYST or ADMIN can create evidence"
        )

    # Enforce unique case_no at validation layer to avoid duplicates on existing DBs
    existing_case = db.query(Evidence).filter(Evidence.case_no == case_no).first()
    if existing_case:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case number must be unique"
        )
    
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be uploaded"
        )
    
    # Validate all files first
    for file in files:
        validate_file(file)
    
    try:
        collected_at_utc = datetime.fromisoformat(collected_at.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid collected_at format. Use ISO-8601"
        )
    
    # Generate unique evidence ID
    evidence_id_str = f"{agency}-{case_no}-{item_no}"
    
    # Check if evidence ID already exists
    existing = db.query(Evidence).filter(Evidence.evidence_id_str == evidence_id_str).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Evidence ID {evidence_id_str} already exists"
        )
    
    # Create evidence record
    evidence = Evidence(
        evidence_id_str=evidence_id_str,
        evidence_name=evidence_name,
        agency=agency,
        case_no=case_no,
        offense=offense,
        item_no=item_no,
        collected_by_user_id=current_user.id,
        badge_no=badge_no,
        location=location,
        collected_at_utc=collected_at_utc,
        description=description
    )
    
    db.add(evidence)
    db.flush()  # Get the ID without committing
    
    # Process and encrypt files
    file_details = []
    evidence_files = []
    
    for file in files:
        # Read file content
        content = await file.read()
        
        # Encrypt and store file
        cipher_path, sha256_hex = encrypt_file_data(content)
        
        # Create file record
        evidence_file = EvidenceFile(
            evidence_id=evidence.id,
            orig_filename=file.filename,
            mime=file.content_type,
            size_bytes=len(content),
            sha256_hex=sha256_hex,
            cipher_path=cipher_path
        )
        
        evidence_files.append(evidence_file)
        file_details.append({
            "filename": file.filename,
            "size_bytes": len(content),
            "sha256": sha256_hex,
            "mime": file.content_type
        })
        
        db.add(evidence_file)
    
    # Create custody record (creator becomes initial custodian)
    custody = Custody(
        evidence_id=evidence.id,
        current_user_id=current_user.id
    )
    db.add(custody)
    
    # Create audit log entry
    audit_details = {
        "action": "EVIDENCE_CREATED",
        "evidence_id_str": evidence_id_str,
        "files": file_details,
        "created_by": current_user.name
    }
    
    audit_entry = create_audit_entry(
        evidence_id=evidence.id,
        actor_user_id=current_user.id,
        action="EVIDENCE_CREATED",
        details=audit_details
    )
    
    audit_log = AuditLog(
        evidence_id=evidence.id,
        actor_user_id=current_user.id,
        action=audit_entry["action"],
        details_json=json.dumps(audit_entry["details"]),
        ts_utc=datetime.fromisoformat(audit_entry["ts_utc"]),
        prev_hash_hex=audit_entry["prev_hash_hex"],
        entry_hash_hex=audit_entry["entry_hash_hex"]
    )
    db.add(audit_log)
    
    db.commit()
    db.refresh(evidence)
    
    # Prepare response
    response = EvidenceResponse.from_orm(evidence)
    response.current_custodian_name = current_user.name
    response.current_custodian_id = current_user.id
    
    return response


@router.get("/", response_model=EvidenceListResponse)
def list_evidence(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List evidence records"""
    query = db.query(Evidence)
    
    # Filter based on user role
    # Only AUDITOR can view all. ADMIN behaves like regular user.
    if current_user.role != UserRole.AUDITOR:
        # Non-admin users can only see evidence they collected or have custody of
        custody_evidence_ids = db.query(Custody.evidence_id).filter(
            Custody.current_user_id == current_user.id
        ).subquery()
        
        query = query.filter(
            (Evidence.collected_by_user_id == current_user.id) |
            (Evidence.id.in_(custody_evidence_ids))
        )
    
    total = query.count()
    evidence_list = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Add custody information
    items = []
    for evidence in evidence_list:
        custody = db.query(Custody).filter(Custody.evidence_id == evidence.id).first()
        custodian = None
        if custody:
            custodian = db.query(User).filter(User.id == custody.current_user_id).first()
        
        item = EvidenceResponse.from_orm(evidence)
        if custodian:
            item.current_custodian_name = custodian.name
            item.current_custodian_id = custodian.id
        
        items.append(item)
    
    return EvidenceListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get evidence details"""
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    custody = db.query(Custody).filter(Custody.evidence_id == evidence_id).first()
    
    if not can_view_evidence(current_user, evidence, custody):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view this evidence"
        )
    
    # Get custodian info
    custodian = None
    if custody:
        custodian = db.query(User).filter(User.id == custody.current_user_id).first()
    
    response = EvidenceResponse.from_orm(evidence)
    if custodian:
        response.current_custodian_name = custodian.name
        response.current_custodian_id = custodian.id
    
    return response


@router.get("/{evidence_id}/download/{file_id}")
async def download_file(
    evidence_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download evidence file (current custodian only)"""
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    evidence_file = db.query(EvidenceFile).filter(
        EvidenceFile.id == file_id,
        EvidenceFile.evidence_id == evidence_id
    ).first()
    if not evidence_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    custody = db.query(Custody).filter(Custody.evidence_id == evidence_id).first()
    
    if not can_download_files(current_user, custody):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only current custodian can download files"
        )
    
    try:
        # Decrypt file
        decrypted_data = decrypt_file_data(evidence_file.cipher_path)
        
        # Verify integrity
        computed_hash = compute_sha256(decrypted_data)
        if computed_hash != evidence_file.sha256_hex:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File integrity check failed"
            )
        
        # Create audit log for file access
        audit_details = {
            "action": "FILE_DOWNLOADED",
            "file_id": file_id,
            "filename": evidence_file.orig_filename,
            "accessed_by": current_user.name
        }
        
        # Get previous hash for audit chain
        prev_audit = db.query(AuditLog).filter(
            AuditLog.evidence_id == evidence_id
        ).order_by(AuditLog.id.desc()).first()
        
        prev_hash = prev_audit.entry_hash_hex if prev_audit else ""
        
        audit_entry = create_audit_entry(
            evidence_id=evidence_id,
            actor_user_id=current_user.id,
            action="FILE_DOWNLOADED",
            details=audit_details,
            prev_hash=prev_hash
        )
        
        audit_log = AuditLog(
            evidence_id=evidence_id,
            actor_user_id=current_user.id,
            action=audit_entry["action"],
            details_json=json.dumps(audit_entry["details"]),
            ts_utc=datetime.fromisoformat(audit_entry["ts_utc"]),
            prev_hash_hex=audit_entry["prev_hash_hex"],
            entry_hash_hex=audit_entry["entry_hash_hex"]
        )
        db.add(audit_log)
        db.commit()
        
        # Stream file response
        return StreamingResponse(
            io.BytesIO(decrypted_data),
            media_type=evidence_file.mime,
            headers={
                "Content-Disposition": f"attachment; filename={evidence_file.orig_filename}"
            }
        )
        
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encrypted file not found on disk"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to decrypt file: {str(e)}"
        )
