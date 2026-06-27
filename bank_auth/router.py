from fastapi import APIRouter

from bank_auth.schemas import UserVerifySchema
from bank_auth.services import verify_user_otp
from services import register_new_user
from schemas import UserRegisterSchema, UserVerifySchema
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