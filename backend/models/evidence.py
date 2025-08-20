from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..db import Base


class Evidence(Base):
    __tablename__ = "evidence"
    
    id = Column(Integer, primary_key=True, index=True)
    evidence_id_str = Column(String(100), unique=True, index=True, nullable=False)
    agency = Column(String(100), nullable=False)
    case_no = Column(String(50), nullable=False, unique=True)
    offense = Column(String(200), nullable=False)
    item_no = Column(String(50), nullable=False)
    collected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    badge_no = Column(String(50), nullable=False)
    location = Column(String(200), nullable=False)
    collected_at_utc = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=False)
    created_at_utc = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    collected_by = relationship("User", foreign_keys=[collected_by_user_id])
    files = relationship("EvidenceFile", back_populates="evidence")
    custody = relationship("Custody", back_populates="evidence", uselist=False)
    transfers = relationship("Transfer", back_populates="evidence")
    audit_logs = relationship("AuditLog", back_populates="evidence")


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    
    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    orig_filename = Column(String(255), nullable=False)
    mime = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256_hex = Column(String(64), nullable=False)
    cipher_path = Column(String(255), nullable=False)
    created_at_utc = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    evidence = relationship("Evidence", back_populates="files")
