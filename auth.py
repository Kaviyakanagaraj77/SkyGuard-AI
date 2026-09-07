"""
SkyGuard AI v2 - Server Security, JWT Authentication & RBAC (Phase 4)
-----------------------------------------------------------------------
Implements secure password hashing (PBKDF2-HMAC-SHA256 with salt), JWT token handling,
Role-Based Access Control (RBAC: ADMIN, OPERATOR, ANALYST, VIEWER), audit logging,
and FastAPI authorization dependencies.
"""

import os
import hashlib
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from database import db_enabled, SessionLocal

# Security Environment Configuration
jwt_secret_env = os.environ.get("JWT_SECRET")
if not jwt_secret_env or jwt_secret_env == "CHANGE_ME_TO_A_RANDOM_32_BYTE_SECRET":
    JWT_SECRET = "skyguard_sih_2026_production_secret_key_32bytes_long"
else:
    JWT_SECRET = jwt_secret_env

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# RBAC Role Definitions
ROLES = ["ADMIN", "OPERATOR", "ANALYST", "VIEWER"]

ROLE_PERMISSIONS = {
    "ADMIN": ["full_access", "user_management", "system_config", "telemetry_read", "alerts_read", "alerts_write", "fleet_read"],
    "OPERATOR": ["telemetry_read", "alerts_read", "alerts_write", "incidents_manage"],
    "ANALYST": ["telemetry_read", "alerts_read", "xai_read", "fleet_read", "reports_read"],
    "VIEWER": ["telemetry_read", "alerts_read", "reports_read"]
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# Pydantic Schemas for Auth & User Management
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str
    username: str


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=6)
    role: str = Field("VIEWER", description="ADMIN, OPERATOR, ANALYST, or VIEWER")


class UserResponse(BaseModel):
    id: Optional[int] = None
    username: str
    email: str
    role: str
    active: bool
    created_at: str


# Cryptographic Password Hashing (PBKDF2-HMAC-SHA256 with Salt)
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split("$")
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected_key = parts[1]
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(key.hex(), expected_key)
    except Exception:
        return False


# JWT Token Generation & Validation
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token.")


# Audit Logging Infrastructure
AUDIT_LOGS: List[Dict[str, Any]] = []


def log_audit_event(event_type: str, username: str, details: str):
    """Records audit trail event (never logs passwords or secrets)."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "username": username,
        "details": details
    }
    AUDIT_LOGS.insert(0, event)
    if len(AUDIT_LOGS) > 500:
        AUDIT_LOGS.pop()


# In-Memory Demo Users Store (Graceful Fallback Mode)
IN_MEMORY_USERS: Dict[str, Dict[str, Any]] = {}


def init_demo_users():
    """Seeds default demo user accounts into memory & database if empty."""
    demo_accounts = [
        ("admin", "admin@skyguard.gov.in", os.environ.get("DEMO_ADMIN_PASSWORD", "AdminPass2026!"), "ADMIN"),
        ("operator", "operator@skyguard.gov.in", os.environ.get("DEMO_OPERATOR_PASSWORD", "OperatorPass2026!"), "OPERATOR"),
        ("analyst", "analyst@skyguard.gov.in", os.environ.get("DEMO_ANALYST_PASSWORD", "AnalystPass2026!"), "ANALYST"),
        ("viewer", "viewer@skyguard.gov.in", os.environ.get("DEMO_VIEWER_PASSWORD", "ViewerPass2026!"), "VIEWER"),
    ]

    for uname, email, plain_pass, role in demo_accounts:
        p_hash = hash_password(plain_pass)
        now_str = datetime.now(timezone.utc).isoformat()
        user_dict = {
            "id": len(IN_MEMORY_USERS) + 1,
            "username": uname,
            "email": email,
            "password_hash": p_hash,
            "role": role,
            "active": True,
            "created_at": now_str
        }
        IN_MEMORY_USERS[uname] = user_dict

        # Seed into SQLAlchemy database if db_enabled is True
        if db_enabled and SessionLocal:
            try:
                from models import UserModel
                session = SessionLocal()
                existing = session.query(UserModel).filter(UserModel.username == uname).first()
                if not existing:
                    u_model = UserModel(
                        username=uname,
                        email=email,
                        password_hash=p_hash,
                        role=role,
                        active=True
                    )
                    session.add(u_model)
                    session.commit()
                session.close()
            except Exception:
                pass


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieves user details by username from database or in-memory store."""
    if db_enabled and SessionLocal:
        try:
            from models import UserModel
            session = SessionLocal()
            row = session.query(UserModel).filter(UserModel.username == username).first()
            session.close()
            if row:
                return {
                    "id": row.id,
                    "username": row.username,
                    "email": row.email,
                    "password_hash": row.password_hash,
                    "role": row.role,
                    "active": row.active,
                    "created_at": row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat()
                }
        except Exception:
            pass

    return IN_MEMORY_USERS.get(username)


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticates username & password against hash."""
    user = get_user_by_username(username)
    if not user:
        log_audit_event("FAILED_LOGIN", username, "Unknown username")
        return None
    if not user.get("active", True):
        log_audit_event("FAILED_LOGIN", username, "User account is inactive")
        return None
    if not verify_password(password, user["password_hash"]):
        log_audit_event("FAILED_LOGIN", username, "Invalid password")
        return None

    log_audit_event("SUCCESSFUL_LOGIN", username, f"Logged in with role {user['role']}")
    return user


# FastAPI Authorization Dependencies
def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[Dict[str, Any]]:
    """Validates JWT bearer token and returns authenticated user details."""
    if not token:
        return None

    payload = decode_access_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User specified in token no longer exists.")
    if not user.get("active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive.")

    return user


def require_role(allowed_roles: List[str]):
    """Returns a dependency checker that enforces specific RBAC roles."""
    def role_checker(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please include a valid 'Authorization: Bearer <token>' header."
            )
        user = get_current_user(token)
        if not user or user["role"] not in allowed_roles:
            username = user["username"] if user else "anonymous"
            log_audit_event("AUTHORIZATION_FAILURE", username, f"Role '{user['role'] if user else 'none'}' denied access to resource requiring {allowed_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden. Action requires one of roles: {', '.join(allowed_roles)}."
            )
        return user
    return role_checker
