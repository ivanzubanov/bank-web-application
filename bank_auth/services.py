import json
import uuid
from datetime import timedelta

import clients
from schemas import UserRegisterSchema, UserVerifySchema, OTPResendSchema, UserLoginSchema, TokenResponseSchema, RefreshTokenRequestSchema
from models import UserTable, UserRefreshTokenTable
from utils import hash_password, generate_otp, verify_password, create_jwt_token, decode_jwt_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status


async def _generate_and_send_otp(user: UserTable) -> str:
    """
    Helper function to generate an OTP, save it to Redis, and send it to Kafka.
    Returns the generated code.
    """
    code = generate_otp()
    redis_key = f"otp:{user.id}"

    await clients.redis_client.set(name=redis_key, value=code, ex=300)

    try:
        event_data = {
            "event_id": str(uuid.uuid4()),
            "email": user.email,
            "otp_code": code,
            "username": user.username
        }
        await clients.kafka_producer.send_and_wait(
            topic="email_verification",
            value=json.dumps(event_data).encode("utf-8")
        )
        print(f"INTERNAL: Verification event sent to Kafka for {user.email}")
    except Exception as e:
        print(f"❌ KAFKA SEND ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending notification. Please, try again later"
        )

    return code

async def register_new_user(
        user_data: UserRegisterSchema,
        db: AsyncSession
):
    query = select(UserTable).where(or_(
        UserTable.username == user_data.username,
        UserTable.email == user_data.email
    ))
    result = await db.execute(query)
    current_user = result.scalar_one_or_none()
    if current_user is not None:
        if current_user.username == user_data.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with such username already exists"
            )
        if current_user.email == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with such email already exists"
            )

    hashed_password = hash_password(user_data.password)
    new_user = UserTable(
        username=user_data.username,
        hashed_password=hashed_password,
        email=user_data.email,
        phone=user_data.phone,
        birth_date=user_data.birth_date,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        patronymic=user_data.patronymic
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await _generate_and_send_otp(new_user)

    return new_user

async def verify_user_otp(data: UserVerifySchema, db: AsyncSession):
    redis_key = f"otp:{data.user_id}"
    saved_code = await clients.redis_client.get(redis_key)

    if not saved_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP code expired or never existed"
        )

    if saved_code != data.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code"
        )

    query = select(UserTable).where(UserTable.id == data.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = True
    await db.commit()

    await clients.redis_client.delete(redis_key)

    try:
        event_data = {
            "event_id": str(uuid.uuid4()),
            "user_id": user.id,
            "username": user.username,
            "email": user.email
        }
        await clients.kafka_producer.send_and_wait(
            topic="user_activated",
            value=json.dumps(event_data).encode("utf-8")
        )
        print(f"INTERNAL: Event UserActivated is sent for user {user.id}")
    except Exception as e:
        print(f"❌ KAFKA ERROR (UserActivated): {e}")

    return {"message": "Account successfully activated"}

async def user_resend_otp(data: OTPResendSchema, db: AsyncSession):
    query = select(UserTable).where(UserTable.id == data.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active"
        )

    await _generate_and_send_otp(user)
    return {"message": "New OTP code sent successfully"}

async def login_user(
        data: UserLoginSchema,
        db: AsyncSession
):
    query = select(UserTable).where(or_(
        UserTable.username == data.username_or_email,
        UserTable.email == data.username_or_email
    ))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/username"
        )
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not activated. Please verify your OTP first"
        )

    user_payload = {"sub": str(user.id), "role": user.role}

    access_token = create_jwt_token(user_payload, timedelta(minutes=15))
    refresh_token = create_jwt_token(user_payload, timedelta(days=30), is_refresh=True)

    db_refresh = UserRefreshTokenTable(user_id=user.id, token=refresh_token)
    db.add(db_refresh)
    await db.commit()

    return TokenResponseSchema(access_token=access_token, refresh_token=refresh_token)

async def refresh_user_tokens(
        data: RefreshTokenRequestSchema,
        db: AsyncSession
) -> TokenResponseSchema:

    payload = decode_jwt_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    user_id = int(payload.get("sub"))

    query = select(UserRefreshTokenTable).where(UserRefreshTokenTable.token == data.refresh_token)
    result = await db.execute(query)
    db_token = result.scalar_one_or_none()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or already revoked"
        )

    await db.delete(db_token)

    user_payload = {"sub": str(user_id), "role": payload.get("role", "USER")}
    new_access_token = create_jwt_token(user_payload, timedelta(minutes=15))
    new_refresh_token = create_jwt_token(user_payload, timedelta(days=30), is_refresh=True)

    new_db_token = UserRefreshTokenTable(user_id=user_id, token=new_refresh_token)
    db.add(new_db_token)

    await db.commit()

    return TokenResponseSchema(access_token=new_access_token, refresh_token=new_refresh_token)



