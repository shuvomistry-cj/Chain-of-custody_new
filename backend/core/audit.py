import json
import hashlib
from typing import Dict, Any, Optional


def compute_entry_hash(prev_hash: str, entry_data: Dict[str, Any]) -> str:
    """
    Compute hash for audit log entry using hash chain
    entry_hash = SHA256(prev_hash || canonical_json(entry_without_hashes))
    """
    # Create canonical JSON (sorted keys, no whitespace)
    canonical_json = json.dumps(entry_data, sort_keys=True, separators=(',', ':'))
    
    # Combine previous hash with canonical JSON
    combined = prev_hash + canonical_json
    
    # Compute SHA256
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def create_audit_entry(
    evidence_id: int,
    actor_user_id: int,
    action: str,
    details: Dict[str, Any],
    prev_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create an audit log entry with hash chain
    """
    from datetime import datetime, timezone
    
    # Use empty string as genesis hash if no previous hash
    if prev_hash is None:
        prev_hash = ""
    
    # Create entry data without hashes
    # Use second-precision timestamp to ensure stable hashing across DB roundtrips
    ts_str = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entry_data = {
        "evidence_id": evidence_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "details": details,
        "ts_utc": ts_str
    }
    
    # Compute entry hash
    entry_hash = compute_entry_hash(prev_hash, entry_data)
    
    # Return complete entry
    return {
        **entry_data,
        "prev_hash_hex": prev_hash,
        "entry_hash_hex": entry_hash
    }
