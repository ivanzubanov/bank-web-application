import json
import uuid
import clients
from schemas import UserRegisterSchema, UserVerifySchema
from models import UserTable
from utils import hash_password, generate_otp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status

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

    code = generate_otp()
    await clients.redis_client.set(name=f"otp:{new_user.id}", value=code, ex=300)

    try:
        event_data = {
            "event_id": str(uuid.uuid4()),
            "email": new_user.email,
            "otp_code": code,
            "username": new_user.username
        }

        message_bytes = json.dumps(event_data).encode("utf-8")

        await clients.kafka_producer.send_and_wait(
            topic="email_verification",
            value=message_bytes
        )
        print(f"INTERNAL: Verification event sent to Kafka for {new_user.email}")

    except Exception as e:
        print(f"❌ KAFKA SEND ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending notification. Please, try again later"
        )

    return new_user

async def verify_user_otp(data: UserVerifySchema, db: AsyncSession):
    redis_key = f"otp:{data.user_id}"
    saved_code = clients.redis_client.get(redis_key)

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

