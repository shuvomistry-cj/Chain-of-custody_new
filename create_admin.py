#!/usr/bin/env python3
"""
One-time script to create an admin user
Usage: python create_admin.py
"""
import os
import sys
from sqlalchemy.orm import Session
from backend.db import SessionLocal, create_tables
from backend.models.user import User, UserRole
from backend.core.security import get_password_hash


def create_admin_user():
    """Create initial admin user"""
    create_tables()
    
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            print(f"Admin user already exists: {existing_admin.email}")
            return
        
        # Get admin details
        name = input("Admin name: ").strip()
        email = input("Admin email: ").strip()
        password = input("Admin password: ").strip()
        
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
