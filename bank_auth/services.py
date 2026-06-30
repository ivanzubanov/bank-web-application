import jwt
import sys
import json
import uuid
import logging
import asyncio
from datetime import timedelta, datetime, timezone

from bank_auth.config import settings
from bank_auth import clients
from bank_auth.schemas import (
    UserRegisterSchema, UserVerifySchema, OTPResendSchema,
    UserLoginSchema, TokenResponseSchema, RefreshTokenRequestSchema,
    UserRoleUpdateSchema, MassMailSchema
)
from bank_auth.models import UserTable, UserRefreshTokenTable
from bank_auth.utils import (
    hash_password, generate_otp, verify_password,
    create_jwt_token, decode_jwt_token
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

async def _generate_and_send_otp(user: UserTable) -> str:
    code = generate_otp()
    redis_key = f"otp:{user.id}"

    await clients.redis_client.set(name=redis_key, value=code, ex=300)

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
    logging.info(f"INTERNAL: Verification event sent to Kafka for {user.email}")
    return code


async def register_new_user(user_data: UserRegisterSchema, db: AsyncSession):
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

    try:
        db.add(new_user)
        await db.flush()

        await _generate_and_send_otp(new_user)

        await db.commit()
        await db.refresh(new_user)
        return new_user

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this credentials already exists"
        )
    except Exception as e:
        await db.rollback()
        logging.error(f"❌ REGISTRATION ERROR (Rolled back): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during registration. Please, try again later"
        )


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

    try:
        user.is_active = True
        await db.flush()

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
        logging.info(f"INTERNAL: Event UserActivated is sent for user {user.id}")

        await clients.redis_client.delete(redis_key)
        await db.commit()

        return {"message": "Account successfully activated"}

    except Exception as e:
        await db.rollback()
        logging.error(f"❌ ACTIVATION ERROR (Rolled back): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Infrastructure error. Activation failed, please try again."
        )


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


async def login_user(data: UserLoginSchema, db: AsyncSession):
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

    user_payload = {"sub": str(user.id), "role": user.role.value}

    access_token = create_jwt_token(user_payload, timedelta(minutes=15))
    refresh_token = create_jwt_token(user_payload, timedelta(days=30), is_refresh=True)

    db_refresh = UserRefreshTokenTable(user_id=user.id, token=refresh_token)
    db.add(db_refresh)
    await db.commit()

    return TokenResponseSchema(access_token=access_token, refresh_token=refresh_token)


async def refresh_user_tokens(data: RefreshTokenRequestSchema, db: AsyncSession) -> TokenResponseSchema:
    payload = await decode_jwt_token(data.refresh_token)

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


async def logout_user(
        refresh_token: RefreshTokenRequestSchema,
        credentials: HTTPAuthorizationCredentials,
        db: AsyncSession
):
    access_token = credentials.credentials
    try:
        payload = jwt.decode(
            access_token,
            settings.public_key,
            algorithms=["RS256"],
            options={"verify_exp": False}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    query = select(UserRefreshTokenTable).where(UserRefreshTokenTable.token == refresh_token.refresh_token)
    result = await db.execute(query)
    current_refresh_token = result.scalar_one_or_none()
    if not current_refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or already revoked refresh token"
        )
    await db.delete(current_refresh_token)

    exp_timestamp = payload.get("exp")
    current_timestamp = datetime.now(timezone.utc).timestamp()
    remaining_ttl = exp_timestamp - current_timestamp
    if remaining_ttl > 0:
        ttl_seconds = int(remaining_ttl) + 1
        redis_key = f"blacklist:{access_token}"
        await clients.redis_client.set(redis_key, "1", ex=ttl_seconds)

    await db.commit()

    return {"detail": "Successfully logged out"}


async def update_user_role(user_id: int, data: UserRoleUpdateSchema, db: AsyncSession):
    query = select(UserTable).where(UserTable.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    old_role = user.role
    user.role = data.role

    try:
        await db.flush()

        event_data = {
            "event_id": str(uuid.uuid4()),
            "user_id": user.id,
            "old_role": old_role.value,
            "new_role": user.role.value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        await clients.kafka_producer.send_and_wait(
            topic="user_status_events",
            value=json.dumps(event_data).encode("utf-8")
        )
        logging.info(f"INTERNAL: Role update event sent to Kafka for user {user.id}")

        await db.commit()
        return {"message": f"User role successfully updated to {user.role.value}"}

    except Exception as e:
        await db.rollback()
        logging.error(f"❌ ROLE UPDATE ERROR (Rolled back): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Infrastructure error. Failed to update role, please try again."
        )


async def mass_mail_users(data: MassMailSchema, db: AsyncSession):
    batch_size = 100
    total_sent = 0
    last_id = 0

    while True:
        query = (
            select(UserTable)
            .where(UserTable.id > last_id)
            .order_by(UserTable.id.asc())
            .limit(batch_size)
        )

        result = await db.execute(query)
        users = result.scalars().all()

        if not users:
            break

        tasks = []
        for user in users:
            user: UserTable
            event_data = {
                "id": str(uuid.uuid4()),
                "email": user.email,
                "username": user.username,
                "subject": data.subject,
                "body": data.body,
                "dispatched_at": datetime.now(timezone.utc).isoformat()
            }

            tasks.append(
                clients.kafka_producer.send_and_wait(
                    topic="admin_mass_mail",
                    value=json.dumps(event_data).encode("utf-8")
                )
            )

        await asyncio.gather(*tasks)

        total_sent += len(users)
        last_id = users[-1].id

    return {
        "status": "success",
        "message": "Mass mail events have been successfully chunked and streamed to Kafka",
        "total_processed_users": total_sent
    }

