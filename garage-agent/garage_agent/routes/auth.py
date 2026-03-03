"""Authentication routes – login and registration."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from garage_agent.core.security import create_access_token
from garage_agent.db.session import get_db
from garage_agent.services.auth_service import authenticate_user, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    garage_id: int
    email: EmailStr
    password: str
    role: str = "OWNER"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreatedResponse(BaseModel):
    id: int
    garage_id: int
    email: str
    role: str


# ── Endpoints ─────────────────────────────────────────────────────────

from garage_agent.core.limiter import limiter
from garage_agent.core.response import success_response


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return a JWT access token."""
    user = authenticate_user(db=db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": str(user.id), "garage_id": user.garage_id})
    return success_response(
        data={"access_token": token, "token_type": "bearer"},
        message="Login successful",
    )


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account."""
    user = create_user(
        db=db,
        garage_id=payload.garage_id,
        email=payload.email,
        password=payload.password,
        role=payload.role,
    )
    return success_response(
        data={
            "id": user.id,
            "garage_id": user.garage_id,
            "email": user.email,
            "role": user.role,
        },
        message="User registered successfully",
    )

