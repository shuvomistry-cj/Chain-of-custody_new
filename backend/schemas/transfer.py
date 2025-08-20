from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..models.transfer import TransferStatus


class TransferRequest(BaseModel):
    evidence_id: int
    to_user_id: int
    reason: str


class TransferResponse(BaseModel):
    id: int
    evidence_id: int
    from_user_id: int
    to_user_id: int
    reason: str
    requested_at_utc: datetime
    accepted_at_utc: Optional[datetime]
    status: TransferStatus
    from_user_name: Optional[str] = None
    to_user_name: Optional[str] = None
    evidence_id_str: Optional[str] = None
    
    class Config:
        from_attributes = True


class CustodyResponse(BaseModel):
    id: int
    evidence_id: int
    current_user_id: int
    since_utc: datetime
    current_user_name: Optional[str] = None
    
    class Config:
        from_attributes = True
