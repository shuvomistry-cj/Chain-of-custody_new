from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from ..db import Base


class TransferStatus(PyEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"


class Custody(Base):
    __tablename__ = "custody"
    
    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), unique=True, nullable=False)
    current_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    since_utc = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    evidence = relationship("Evidence", back_populates="custody")
    current_user = relationship("User", foreign_keys=[current_user_id])


class Transfer(Base):
    __tablename__ = "transfers"
    
    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=False)
    requested_at_utc = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at_utc = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(TransferStatus), default=TransferStatus.PENDING, nullable=False)
    
    # Relationships
    evidence = relationship("Evidence", back_populates="transfers")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
