from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class AnalysisFileResponse(BaseModel):
    id: int
    orig_filename: str
    mime: str
    size_bytes: int
    sha256_hex: str
    created_at_utc: datetime

    class Config:
        from_attributes = True


class AnalysisCreate(BaseModel):
    evidence_id: int
    analysis_at_iso: str  # ISO datetime in UTC
    analysis_by: str
    role: str
    place_of_analysis: str
    description: str


class AnalysisResponse(BaseModel):
    id: int
    evidence_id: int
    analysis_at_utc: datetime
    analysis_by: str
    role: str
    place_of_analysis: str
    description: str
    created_by_user_id: int
    created_at_utc: datetime
    files: List[AnalysisFileResponse] = []

    class Config:
        from_attributes = True


class AnalysisListResponse(BaseModel):
    items: List[AnalysisResponse]
    total: int
