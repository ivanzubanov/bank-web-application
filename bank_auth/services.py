import json
import uuid
import clients
from schemas import UserRegisterSchema
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

