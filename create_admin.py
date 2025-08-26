#!/usr/bin/env python3
"""
One-time script to create an admin user
Usage: python create_admin.py

Non-interactive mode for cloud providers (e.g., Render):
  Provide these environment variables and run the script once:
    ADMIN_NAME
    ADMIN_EMAIL
    ADMIN_PASSWORD

  Example values you can set on Render:
    ADMIN_NAME=shuvo
    ADMIN_EMAIL=shuvo@gmail.com
    ADMIN_PASSWORD=shuvomitro339

If any of the environment variables are missing, the script will prompt
interactively (useful for local development).
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from backend.db import SessionLocal, create_tables
from backend.models.user import User, UserRole
from backend.core.security import get_password_hash


def create_admin_user():
    """Create initial admin user"""
    # Load environment from local .env
    try:
        load_dotenv()
    except Exception:
        pass
    # Load Render Secret File if present
    try:
        if os.path.exists("/etc/secrets/admin.env"):
            load_dotenv("/etc/secrets/admin.env")
    except Exception:
        pass

    create_tables()
    
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            print(f"Admin user already exists: {existing_admin.email}")
            return
        
        # Try env vars first (non-interactive mode)
        name = os.getenv("ADMIN_NAME", "").strip()
        email = os.getenv("ADMIN_EMAIL", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "").strip()

        # If missing and running non-interactively (e.g., Render), do NOT prompt; exit with message
        if not all([name, email, password]) and not sys.stdin.isatty():
            def mask(v: str) -> str:
                return "<set>" if v else "<missing>"
            print("Admin seeding (non-interactive) - env var status:")
            print(f"  ADMIN_NAME: {mask(name)}")
            print(f"  ADMIN_EMAIL: {mask(email)}")
            print(f"  ADMIN_PASSWORD: {mask(password)}")
            print("One or more admin environment variables are missing. Aborting without prompts.")
            sys.exit(1)

        # If interactive (local), prompt for any missing values
        if not all([name, email, password]):
            print("Environment variables not fully provided; falling back to prompts...")
            name = name or input("Admin name: ").strip()
            email = email or input("Admin email: ").strip()
            password = password or input("Admin password: ").strip()
        
        if not all([name, email, password]):
            print("All fields are required!")
            return
        
        # Create admin user
        admin_user = User(
            name=name,
            email=email,
            role=UserRole.ADMIN,
            password_hash=get_password_hash(password)
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"Admin user created successfully!")
        print(f"ID: {admin_user.id}")
        print(f"Name: {admin_user.name}")
        print(f"Email: {admin_user.email}")
        print(f"Role: {admin_user.role.value}")
        
    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
