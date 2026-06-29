import pytest
import datetime
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from fastapi import status

from tests.conftest import TestingSessionLocal
from bank_auth.models import UserTable, UserRefreshTokenTable
from bank_auth.utils import hash_password, create_jwt_token


@pytest.mark.asyncio
async def test_full_registration_and_activation_flow(ac: AsyncClient):
    user_payload = {
        "username": "test_warrior",
        "email": "warrior@example.com",
        "password": "secure_password_123",
        "phone": "+375291112233",
        "birth_date": "1995-05-15",
        "first_name": "John",
        "last_name": "Doe",
        "age": 31
    }

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis, \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock) as mock_kafka:
        reg_response = await ac.post("/auth/register", json=user_payload)
        assert reg_response.status_code == status.HTTP_200_OK

        user_data = reg_response.json()
        user_id = user_data["id"]
        assert user_data["is_active"] is False

        mock_redis.get.return_value = "123456"

        verify_payload = {
            "user_id": user_id,
            "code": "123456"
        }

        verify_response = await ac.post("/auth/verify-otp", json=verify_payload)

        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.json()["message"] == "Account successfully activated"

        mock_redis.get.assert_called_once_with(f"otp:{user_id}")
        mock_redis.delete.assert_called_once_with(f"otp:{user_id}")

        assert mock_kafka.send_and_wait.called


@pytest.mark.asyncio
async def test_register_age_restriction(ac: AsyncClient):
    underage_payload = {
        "username": "kid_pro",
        "email": "kid@example.com",
        "password": "password123",
        "phone": "+375290000000",
        "birth_date": "2018-01-01",
        "first_name": "Baby",
        "last_name": "Yoda",
        "age": 8
    }
    response = await ac.post("/auth/register", json=underage_payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_register_exact_age_boundary_success(ac: AsyncClient):
    today = datetime.date.today()
    try:
        exact_14_years_ago = today.replace(year=today.year - 14)
    except ValueError:
        exact_14_years_ago = today.replace(year=today.year - 14, day=28)

    payload = {
        "username": "young_warrior",
        "email": "young@example.com",
        "password": "secure_password_123",
        "phone": "+375292223344",
        "birth_date": exact_14_years_ago.isoformat(),
        "first_name": "Alex",
        "last_name": "Smith",
        "age": 14,
    }

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/register", json=payload)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_register_underage_by_one_day_failure(ac: AsyncClient):
    today = datetime.date.today()
    underage_by_day = today.replace(year=today.year - 14) + datetime.timedelta(days=1)

    payload = {
        "username": "almost_adult",
        "email": "almost@example.com",
        "password": "secure_password_123",
        "phone": "+375293334455",
        "birth_date": underage_by_day.isoformat(),
        "first_name": "Baby",
        "last_name": "Yoda",
        "age": 13,
    }

    response = await ac.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_register_duplicate_username_failure(ac: AsyncClient):
    payload_1 = {
        "username": "clone_warrior",
        "email": "original@example.com",
        "password": "password123",
        "phone": "+375294445566",
        "birth_date": "1990-01-01",
        "first_name": "John",
        "last_name": "Doe",
        "age": 36,
    }
    payload_2 = payload_1.copy()
    payload_2["email"] = "clone@example.com"
    payload_2["phone"] = "+375295556677"

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        res1 = await ac.post("/auth/register", json=payload_1)
        assert res1.status_code == status.HTTP_200_OK

        res2 = await ac.post("/auth/register", json=payload_2)
        assert res2.status_code == status.HTTP_409_CONFLICT
        assert res2.json()["detail"] == "User with such username already exists"


@pytest.mark.asyncio
async def test_register_duplicate_email_failure(ac: AsyncClient):
    payload_1 = {
        "username": "first_user",
        "email": "same_email@example.com",
        "password": "password123",
        "phone": "+375296667788",
        "birth_date": "1990-01-01",
        "first_name": "First",
        "last_name": "User",
        "age": 36,
    }
    payload_2 = payload_1.copy()
    payload_2["username"] = "second_user"
    payload_2["phone"] = "+375297778899"

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        res1 = await ac.post("/auth/register", json=payload_1)
        assert res1.status_code == status.HTTP_200_OK

        res2 = await ac.post("/auth/register", json=payload_2)
        assert res2.status_code == status.HTTP_409_CONFLICT
        assert res2.json()["detail"] == "User with such email already exists"


@pytest.mark.asyncio
async def test_verify_otp_invalid_code_failure(ac: AsyncClient):
    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.get.return_value = "123456"

        verify_payload = {"user_id": 999, "code": "654321"}

        response = await ac.post("/auth/verify-otp", json=verify_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == "Invalid OTP code"


@pytest.mark.asyncio
async def test_verify_otp_expired_or_missing_failure(ac: AsyncClient):
    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.get.return_value = None

        verify_payload = {"user_id": 999, "code": "123456"}

        response = await ac.post("/auth/verify-otp", json=verify_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == "OTP code expired or never existed"


@pytest.mark.asyncio
async def test_resend_otp_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="resend_warrior", email="resend@example.com",
            hashed_password="123", phone="+375298881122",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/verify-otp/resend", json={"user_id": user_id})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "New OTP code sent successfully"


@pytest.mark.asyncio
async def test_login_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="login_warrior", email="login@example.com",
            hashed_password=hash_password("correct_password"), phone="+375298883344",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B",
            is_active=True
        )
        session.add(user)
        await session.commit()

    login_payload = {
        "username_or_email": "login_warrior",
        "password": "correct_password"
    }

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_unauthorized_wrong_password(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="wrong_pass_user", email="wrong_pass@example.com",
            hashed_password=hash_password("correct_password"), phone="+375298884455",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B",
            is_active=True
        )
        session.add(user)
        await session.commit()

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/login", json={
            "username_or_email": "wrong_pass_user",
            "password": "invalid_password_here"
        })
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid password"


@pytest.mark.asyncio
async def test_login_forbidden_not_activated(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="not_active_user", email="not_active@example.com",
            hashed_password=hash_password("password123"), phone="+375298885566",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B",
            is_active=False
        )
        session.add(user)
        await session.commit()

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/login", json={
            "username_or_email": "not_active_user",
            "password": "password123"
        })
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "verify your OTP first" in response.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_tokens_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="refresh_warrior", email="refresh_flow@example.com",
            hashed_password="123", phone="+375298886677",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B",
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        user_payload = {"sub": str(user.id), "role": user.role}
        refresh_token = create_jwt_token(user_payload, datetime.timedelta(days=30), is_refresh=True)

        db_token = UserRefreshTokenTable(user_id=user.id, token=refresh_token)
        session.add(db_token)
        await session.commit()

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock), \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_token