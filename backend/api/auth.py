from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..db import get_db
from ..models.user import User, UserRole
from ..models.user_profile import UserProfile
from ..schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    TokenRefresh,
    UserResponse,
    UserUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from ..core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, verify_token

router = APIRouter()
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    token = credentials.credentials
    payload = verify_token(token, "access")
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


def require_role(required_role: UserRole):
    """Decorator to require specific user role"""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {required_role.value} role"
            )
        return current_user
    return role_checker


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require ADMIN role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires ADMIN role"
        )
    return current_user


@router.post("/register", response_model=UserResponse)
def register_user(
    user_data: UserRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Register a new user (ADMIN only)"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        name=user_data.name,
        email=user_data.email,
        role=user_data.role,
        password_hash=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Create profile if any optional fields provided
    if any([
        user_data.organization,
        user_data.department,
        user_data.employee_id,
        user_data.national_id,
        user_data.authorised_by,
        user_data.photo_url,
    ]):
        profile = UserProfile(
            user_id=db_user.id,
            organization=user_data.organization,
            department=user_data.department,
            employee_id=user_data.employee_id,
            national_id=user_data.national_id,
            authorised_by=user_data.authorised_by,
            photo_url=user_data.photo_url,
        )
        db.add(profile)
        db.commit()

    return db_user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login and get access/refresh tokens"""
    user = db.query(User).filter(User.email == user_data.email).first()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=Token)
def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """Refresh access token using refresh token"""
    payload = verify_token(token_data.refresh_token, "refresh")
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@router.get("/users", response_model=list[UserResponse])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all registered users (basic info). Accessible to any authenticated user.
    Returns id, name, email, role, created_at.
    """
    users = db.query(User).order_by(User.name.asc()).all()
    return users


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update limited user fields (ADMIN only). Currently supports role changes only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Only update fields that exist in the current model
    if payload.role is not None:
        user.role = payload.role

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}/profile", response_model=UserProfileResponse)
def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a user's profile. Admins can view anyone; users can view their own."""
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        # Return an empty profile shape
        return UserProfileResponse(
            user_id=user_id,
            organization=None,
            department=None,
            employee_id=None,
            national_id=None,
            authorised_by=None,
            photo_url=None,
        )
    return profile


@router.get("/me/profile", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        return UserProfileResponse(
            user_id=current_user.id,
            organization=None,
            department=None,
            employee_id=None,
            national_id=None,
            authorised_by=None,
            photo_url=None,
        )
    return profile


@router.patch("/users/{user_id}/profile", response_model=UserProfileResponse)
def update_user_profile(
    user_id: int,
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin: update or create a user's profile."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.flush()

    if payload.organization is not None:
        profile.organization = payload.organization
    if payload.department is not None:
        profile.department = payload.department
    if payload.employee_id is not None:
        profile.employee_id = payload.employee_id
    if payload.national_id is not None:
        profile.national_id = payload.national_id
    if payload.authorised_by is not None:
        profile.authorised_by = payload.authorised_by
    if payload.photo_url is not None:
        profile.photo_url = payload.photo_url

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
