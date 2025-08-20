from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class EvidenceFileResponse(BaseModel):
    id: int
    orig_filename: str
    mime: str
    size_bytes: int
    sha256_hex: str
    created_at_utc: datetime
    
    class Config:
        from_attributes = True


class EvidenceResponse(BaseModel):
    id: int
    evidence_id_str: str
    agency: str
    case_no: str
    offense: str
    item_no: str
    collected_by_user_id: int
    badge_no: str
    location: str
    collected_at_utc: datetime
    description: str
    created_at_utc: datetime
    files: List[EvidenceFileResponse] = []
    current_custodian_name: Optional[str] = None
    current_custodian_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class EvidenceListResponse(BaseModel):
    items: List[EvidenceResponse]
    total: int
    page: int
    per_page: int
