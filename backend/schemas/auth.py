from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from ..models.user import UserRole


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    role: UserRole
    password: str
    # Optional profile fields
    organization: Optional[str] = None
    department: Optional[str] = None
    employee_id: Optional[str] = None
    national_id: Optional[str] = None
    authorised_by: Optional[str] = None
    photo_url: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None


class UserProfileResponse(BaseModel):
    user_id: int
    organization: Optional[str] = None
    department: Optional[str] = None
    employee_id: Optional[str] = None
    national_id: Optional[str] = None
    authorised_by: Optional[str] = None
    photo_url: Optional[str] = None


class UserProfileUpdate(BaseModel):
    organization: Optional[str] = None
    department: Optional[str] = None
    employee_id: Optional[str] = None
    national_id: Optional[str] = None
    authorised_by: Optional[str] = None
    photo_url: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
