from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserOut
from app.modules.auth.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id, extra={"org_id": user.organization_id, "email": user.email})
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_user: User = Depends(get_current_user)) -> None:
    # JWT is stateless; client discards the token. Endpoint exists for API completeness.
    return None


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
