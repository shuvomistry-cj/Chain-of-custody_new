from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from ..db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    organization = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    employee_id = Column(String(255), nullable=True)
    national_id = Column(String(255), nullable=True)
    authorised_by = Column(String(255), nullable=True)
    photo_url = Column(String(512), nullable=True)
