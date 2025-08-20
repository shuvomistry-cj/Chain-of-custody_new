from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..db import Base


class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False, index=True)
    analysis_at_utc = Column(DateTime(timezone=True), nullable=False)
    analysis_by = Column(String(200), nullable=False)
    role = Column(String(100), nullable=False)
    place_of_analysis = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at_utc = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("Evidence")
    created_by = relationship("User")
    files = relationship("AnalysisFile", back_populates="analysis")


class AnalysisFile(Base):
    __tablename__ = "analysis_files"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analysis.id"), nullable=False)
    orig_filename = Column(String(255), nullable=False)
    mime = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256_hex = Column(String(64), nullable=False)
    cipher_path = Column(String(255), nullable=False)
    created_at_utc = Column(DateTime(timezone=True), server_default=func.now())

    analysis = relationship("Analysis", back_populates="files")
