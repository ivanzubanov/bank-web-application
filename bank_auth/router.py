from fastapi import APIRouter

from services import (
    register_new_user, user_resend_otp, verify_user_otp,
    login_user, refresh_user_tokens
)
from schemas import (
    UserRegisterSchema, UserVerifySchema, OTPResendSchema,
    UserLoginSchema, RefreshTokenRequestSchema, TokenResponseSchema
)
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from fastapi import Depends

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

@router.post("/register")
async def register_new_user_endpoint(
        user_data: UserRegisterSchema,
        db: AsyncSession = Depends(get_db)
):
    return await register_new_user(user_data, db)

@router.post("/verify-otp")
async def verify_user_otp_endpoint(
        data: UserVerifySchema,
        db: AsyncSession = Depends(get_db)
):
    return await verify_user_otp(data, db)

@router.post("/verify-otp/resend")
async def user_resend_otp_endpoint(
        data: OTPResendSchema,
        db: AsyncSession = Depends(get_db)
):
    return await user_resend_otp(data, db)

@router.post("/login", response_model=TokenResponseSchema)
async def login_user_endpoint(
        data: UserLoginSchema,
        db: AsyncSession = Depends(get_db)
):
    return await login_user(data, db)

@router.post("/refresh", response_model=TokenResponseSchema)
async def refresh_user_tokens_endpoint(
        data: RefreshTokenRequestSchema,
        db: AsyncSession = Depends(get_db)
):
    return await refresh_user_tokens(data, db)

