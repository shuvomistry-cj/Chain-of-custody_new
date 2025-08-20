from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
from ..db import get_db
from ..models.user import User, UserRole
from ..models.evidence import Evidence
from ..models.audit import AuditLog
from ..api.auth import get_current_user

router = APIRouter()


class AuditEntryResponse:
    def __init__(self, audit_log: AuditLog, actor_name: str):
        self.id = audit_log.id
        self.evidence_id = audit_log.evidence_id
        self.actor_user_id = audit_log.actor_user_id
        self.actor_name = actor_name
        self.action = audit_log.action
        self.details = json.loads(audit_log.details_json)
        self.ts_utc = audit_log.ts_utc
        self.prev_hash_hex = audit_log.prev_hash_hex
        self.entry_hash_hex = audit_log.entry_hash_hex


@router.get("/{evidence_id}")
def get_audit_log(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get audit log for evidence (all roles can access)"""
    # Verify evidence exists
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Get audit logs in chronological order
    audit_logs = db.query(AuditLog).filter(
        AuditLog.evidence_id == evidence_id
    ).order_by(AuditLog.id.asc()).all()
    
    # Build response with actor names
    response = []
    for log in audit_logs:
        actor = db.query(User).filter(User.id == log.actor_user_id).first()
        actor_name = actor.name if actor else "Unknown"
        # Normalize timestamp to UTC-aware, second precision for display consistency
        from datetime import timezone
        ts_display = log.ts_utc
        if ts_display is not None:
            if ts_display.tzinfo is None:
                ts_display = ts_display.replace(tzinfo=timezone.utc)
            ts_display = ts_display.replace(microsecond=0)
        
        entry = {
            "id": log.id,
            "evidence_id": log.evidence_id,
            "actor_user_id": log.actor_user_id,
            "actor_name": actor_name,
            "action": log.action,
            "details": json.loads(log.details_json),
            "ts_utc": ts_display.isoformat() if ts_display is not None else None,
            "prev_hash_hex": log.prev_hash_hex,
            "entry_hash_hex": log.entry_hash_hex
        }
        response.append(entry)
    
    return {
        "evidence_id": evidence_id,
        "evidence_id_str": evidence.evidence_id_str,
        "audit_entries": response,
        "total_entries": len(response)
    }


@router.get("/{evidence_id}/verify")
def verify_audit_chain(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify the integrity of the audit hash chain"""
    from ..core.audit import compute_entry_hash
    
    # Verify evidence exists
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Get audit logs in chronological order
    audit_logs = db.query(AuditLog).filter(
        AuditLog.evidence_id == evidence_id
    ).order_by(AuditLog.id.asc()).all()
    
    if not audit_logs:
        return {
            "evidence_id": evidence_id,
            "evidence_id_str": evidence.evidence_id_str,
            "chain_valid": True,
            "total_entries": 0,
            "verification_details": []
        }
    
    verification_details = []
    chain_valid = True
    expected_prev_hash = ""
    
    for i, log in enumerate(audit_logs):
        # Reconstruct entry data without hashes
        from datetime import timezone
        ts_for_hash = log.ts_utc
        if ts_for_hash is not None:
            # Force UTC tzinfo if missing and use second precision to match hashing
            if ts_for_hash.tzinfo is None:
                ts_for_hash = ts_for_hash.replace(tzinfo=timezone.utc)
            ts_for_hash = ts_for_hash.replace(microsecond=0)
        entry_data = {
            "evidence_id": log.evidence_id,
            "actor_user_id": log.actor_user_id,
            "action": log.action,
            "details": json.loads(log.details_json),
            "ts_utc": ts_for_hash.isoformat() if ts_for_hash is not None else None
        }
        
        # Verify previous hash
        prev_hash_valid = log.prev_hash_hex == expected_prev_hash
        
        # Compute expected entry hash
        expected_entry_hash = compute_entry_hash(log.prev_hash_hex, entry_data)
        entry_hash_valid = log.entry_hash_hex == expected_entry_hash
        
        entry_valid = prev_hash_valid and entry_hash_valid
        if not entry_valid:
            chain_valid = False
        
        verification_details.append({
            "entry_id": log.id,
            "sequence": i + 1,
            "action": log.action,
            "ts_utc": ts_for_hash.isoformat() if ts_for_hash is not None else None,
            "prev_hash_valid": prev_hash_valid,
            "entry_hash_valid": entry_hash_valid,
            "entry_valid": entry_valid,
            "expected_prev_hash": expected_prev_hash,
            "actual_prev_hash": log.prev_hash_hex,
            "expected_entry_hash": expected_entry_hash,
            "actual_entry_hash": log.entry_hash_hex
        })
        
        # Set up for next iteration
        expected_prev_hash = log.entry_hash_hex
    
    return {
        "evidence_id": evidence_id,
        "evidence_id_str": evidence.evidence_id_str,
        "chain_valid": chain_valid,
        "total_entries": len(audit_logs),
        "verification_details": verification_details
    }
