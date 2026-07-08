import hashlib
from src.db.database import SessionLocal
from src.db.models import User


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def authenticate_user(user_id: str, password: str) -> dict | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(user_id=user_id).first()
        if user and verify_password(password, user.password_hash):
            return {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
                "name": user.name,
                "email": user.email or "",
                "department_id": user.department_id or "",
            }
        return None
    finally:
        db.close()


def register_user(username: str, password: str, name: str, email: str,
                  department_id: str, role: str = 'employee') -> str:
    db = SessionLocal()
    try:
        if not email or not email.strip():
            return "邮箱不能为空"
            
        if db.query(User).filter_by(username=username).first():
            return f"用户名 {username} 已存在"
        user_id = f"U{db.query(User).count() + 1:04d}"
        user = User(
            user_id=user_id,
            username=username,
            password_hash=hash_password(password),
            role=role,
            name=name,
            email=email,
            department_id=department_id,
        )
        db.add(user)
        db.commit()
        return f"注册成功！用户ID: {user_id}"
    except Exception as e:
        db.rollback()
        return f"注册失败：{str(e)}"
    finally:
        db.close()


def get_user_by_id(user_id: str) -> dict | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(user_id=user_id).first()
        if user:
            return {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
                "name": user.name,
                "email": user.email or "",
                "department_id": user.department_id or "",
            }
        return None
    finally:
        db.close()
