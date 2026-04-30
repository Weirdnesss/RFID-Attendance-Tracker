"""
auth_db.py
----------
User authentication and management for the RFID Attendance Tracker.
"""

import bcrypt
from database import SessionLocal, User


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def authenticate(username: str, password: str) -> dict | None:
    """
    Returns user dict if credentials are valid, None otherwise.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return {
            "id":       user.id,
            "username": user.username,
            "role":     user.role,
        }
    finally:
        db.close()


def create_user(username: str, password: str, role: str) -> tuple[bool, str]:
    """
    Creates a new user. Returns (success, message).
    """
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return False, f"Username '{username}' already exists."

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
        db.commit()
        return True, f"User '{username}' created successfully."
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def seed_superadmin(username: str = "superadmin2", password: str = "admin1234"):
    """
    Creates the superadmin account if it doesn't already exist.
    Called once on app startup.
    """
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="superadmin",
        )
        db.add(user)
        db.commit()
        print(f"Superadmin seeded — username: '{username}' password: '{password}'")
    except Exception as e:
        db.rollback()
        print(f"Failed to seed superadmin: {e}")
    finally:
        db.close()