from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(100), nullable=False)
    details_json = Column(Text, nullable=False)
    ts_utc = Column(DateTime(timezone=True), server_default=func.now())
    prev_hash_hex = Column(String(64), nullable=False)
    entry_hash_hex = Column(String(64), nullable=False)
    
    # Relationships
    evidence = relationship("Evidence", back_populates="audit_logs")
    actor = relationship("User", foreign_keys=[actor_user_id])
