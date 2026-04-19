"""Digital Force — Auth API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
from database import get_db, User
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""
    role: str = "operator"

@router.post("/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Username already exists")
    user = User(
        id=str(uuid.uuid4()), username=body.username, email=body.email,
        full_name=body.full_name, hashed_password=hash_password(body.password), role=body.role,
    )
    db.add(user)
    await db.flush()
    token = create_access_token({"sub": user.id, "username": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role}}

@router.options("/login")
async def login_options(request: fastapi.Request):
    import logging
    log = logging.getLogger(__name__)
    log.error("=== OPTIONS PREFLIGHT HEADERS RECEIVED ===")
    for k, v in request.headers.items():
        log.error(f"  {k}: {v}")
    
    # Bypass Starlette's strict 400 Bad Request and just return 200 with wildcard allowing EVERYTHING
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("OK", status_code=200, headers={
        "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE, PATCH",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
        "Access-Control-Allow-Credentials": "true"
    })

@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Accept either email or username
    from sqlalchemy import or_
    result = await db.execute(
        select(User).where(or_(User.email == body.email, User.username == body.email))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    user.last_login = datetime.utcnow()
    token = create_access_token({"sub": user.id, "username": user.username, "role": user.role, "email": user.email, "full_name": user.full_name})
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "full_name": user.full_name}}

@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user

class ProfileUpdate(BaseModel):
    full_name: str

@router.patch("/me")
async def update_my_profile(body: ProfileUpdate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user.get("sub")))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    db_user.full_name = body.full_name
    await db.commit()
    
    # Return the updated metadata so frontend can update its store
    return {"status": "success", "full_name": db_user.full_name, "email": db_user.email}
