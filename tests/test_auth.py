import pytest
import datetime
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from httpx import AsyncClient
from fastapi import status

from tests.conftest import TestingSessionLocal
from bank_auth.models import UserTable, UserRefreshTokenTable, UserRole
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

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis, \
            patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        mock_redis.exists.return_value = False

        response = await ac.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_logout_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        user = UserTable(
            username="logout_warrior", email="logout_flow@example.com",
            hashed_password="123", phone="+375299990011",
            birth_date=datetime.date(1990, 1, 1), first_name="A", last_name="B",
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        user_payload = {"sub": str(user.id), "role": user.role}
        access_token = create_jwt_token(user_payload, datetime.timedelta(minutes=15))
        refresh_token = create_jwt_token(user_payload, datetime.timedelta(days=30), is_refresh=True)

        db_token = UserRefreshTokenTable(user_id=user.id, token=refresh_token)
        session.add(db_token)
        await session.commit()

    headers = {"Authorization": f"Bearer {access_token}"}
    logout_payload = {"refresh_token": refresh_token}

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis:
        response = await ac.post("/auth/logout", json=logout_payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["detail"] == "Successfully logged out"

        assert mock_redis.set.called
        called_key = mock_redis.set.call_args[1].get('name') or mock_redis.set.call_args[0][0]
        assert called_key == f"blacklist:{access_token}"

    async with TestingSessionLocal() as session:
        from sqlalchemy import select
        query = select(UserRefreshTokenTable).where(UserRefreshTokenTable.token == refresh_token)
        result = await session.execute(query)
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_logout_invalid_access_token_failure(ac: AsyncClient):
    headers = {"Authorization": "Bearer invalid_and_broken_token_string"}
    logout_payload = {"refresh_token": "some_refresh_token"}

    response = await ac.post("/auth/logout", json=logout_payload, headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid token"


@pytest.mark.asyncio
async def test_logout_wrong_token_type_failure(ac: AsyncClient):
    user_payload = {"sub": "1", "role": "USER"}
    refresh_token_as_access = create_jwt_token(user_payload, datetime.timedelta(days=30), is_refresh=True)

    headers = {"Authorization": f"Bearer {refresh_token_as_access}"}
    logout_payload = {"refresh_token": refresh_token_as_access}

    response = await ac.post("/auth/logout", json=logout_payload, headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid token type"


@pytest.mark.asyncio
async def test_logout_refresh_token_not_found_failure(ac: AsyncClient):
    user_payload = {"sub": "1", "role": "USER"}
    access_token = create_jwt_token(user_payload, datetime.timedelta(minutes=15))
    non_existent_refresh = create_jwt_token(user_payload, datetime.timedelta(days=30), is_refresh=True)

    headers = {"Authorization": f"Bearer {access_token}"}
    logout_payload = {"refresh_token": non_existent_refresh}

    response = await ac.post("/auth/logout", json=logout_payload, headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid or already revoked refresh token" in response.json()["detail"]

# UPDATE USER ROLE

@pytest.mark.asyncio
async def test_change_user_role_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_boss",
            email="admin@example.com",
            hashed_password="123",
            phone="+375291111111",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Main",
            is_active=True,
            role=UserRole.ADMIN,
        )
        target = UserTable(
            username="target_user",
            email="target@example.com",
            hashed_password="123",
            phone="+375292222222",
            birth_date=datetime.date(1995, 1, 1),
            first_name="Target",
            last_name="User",
            is_active=True,
            role=UserRole.USER,
        )
        session.add_all([admin, target])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(target)
        admin_id = admin.id
        target_id = target.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis, patch(
        "bank_auth.clients.kafka_producer", new_callable=AsyncMock
    ) as mock_kafka:
        mock_redis.exists.return_value = False

        response = await ac.patch(
            f"/admin/users/{target_id}/role",
            json={"role": "ADMIN"},
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert mock_kafka.send_and_wait.called

    async with TestingSessionLocal() as session:
        query = select(UserTable).where(UserTable.id == target_id)
        result = await session.execute(query)
        updated_user = result.scalar_one()
        assert updated_user.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_change_user_role_forbidden_for_regular_user(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        regular = UserTable(
            username="regular_user",
            email="regular@example.com",
            hashed_password="123",
            phone="+375293333333",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Regular",
            last_name="User",
            is_active=True,
            role=UserRole.USER,
        )
        session.add(regular)
        await session.commit()
        await session.refresh(regular)
        regular_id = regular.id

    regular_payload = {"sub": str(regular_id), "role": UserRole.USER.value}
    access_token = create_jwt_token(regular_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis:
        mock_redis.exists.return_value = False

        response = await ac.patch(
            f"/admin/users/{regular_id}/role",
            json={"role": "ADMIN"},
            headers=headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_change_user_role_not_found(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_boss_2",
            email="admin2@example.com",
            hashed_password="123",
            phone="+375294444444",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Two",
            is_active=True,
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis:
        mock_redis.exists.return_value = False

        response = await ac.patch(
            "/admin/users/99999/role", json={"role": "ADMIN"}, headers=headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_change_user_role_infrastructure_failure_rollback(
    ac: AsyncClient,
):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_boss_3",
            email="admin3@example.com",
            hashed_password="123",
            phone="+375295555555",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Three",
            is_active=True,
            role=UserRole.ADMIN,
        )
        target = UserTable(
            username="target_user_rollback",
            email="target_rollback@example.com",
            hashed_password="123",
            phone="+375296666666",
            birth_date=datetime.date(1995, 1, 1),
            first_name="Target",
            last_name="Rollback",
            is_active=True,
            role=UserRole.USER,
        )
        session.add_all([admin, target])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(target)
        admin_id = admin.id
        target_id = target.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis, patch(
        "bank_auth.clients.kafka_producer", new_callable=AsyncMock
    ) as mock_kafka:
        mock_redis.exists.return_value = False
        mock_kafka.send_and_wait.side_effect = Exception("Kafka down")

        response = await ac.patch(
            f"/admin/users/{target_id}/role",
            json={"role": "ADMIN"},
            headers=headers,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    async with TestingSessionLocal() as session:
        query = select(UserTable).where(UserTable.id == target_id)
        result = await session.execute(query)
        rolled_back_user = result.scalar_one()
        assert rolled_back_user.role == UserRole.USER

# MASS MAIL SEND

@pytest.mark.asyncio
async def test_mass_mail_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_mass",
            email="admin_mass@example.com",
            hashed_password="123",
            phone="+375291111112",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Mass",
            is_active=True,
            role=UserRole.ADMIN,
        )
        user1 = UserTable(
            username="user_mass_1",
            email="user1@example.com",
            hashed_password="123",
            phone="+375292222223",
            birth_date=datetime.date(1995, 1, 1),
            first_name="User",
            last_name="One",
            is_active=True,
            role=UserRole.USER,
        )
        user2 = UserTable(
            username="user_mass_2",
            email="user2@example.com",
            hashed_password="123",
            phone="+375292222224",
            birth_date=datetime.date(1995, 1, 1),
            first_name="User",
            last_name="Two",
            is_active=True,
            role=UserRole.USER,
        )
        session.add_all([admin, user1, user2])
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    mail_payload = {
        "subject": "Test Subject",
        "body": "Test Body Content"
    }

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis, \
         patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock) as mock_kafka:
        mock_redis.exists.return_value = False

        response = await ac.post(
            "/admin/mass-mail",
            json=mail_payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["total_processed_users"] == 3
        assert mock_kafka.send_and_wait.call_count == 3


@pytest.mark.asyncio
async def test_mass_mail_forbidden_for_regular_user(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        regular = UserTable(
            username="regular_mass",
            email="regular_mass@example.com",
            hashed_password="123",
            phone="+375293333334",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Regular",
            last_name="Mass",
            is_active=True,
            role=UserRole.USER,
        )
        session.add(regular)
        await session.commit()
        await session.refresh(regular)
        regular_id = regular.id

    regular_payload = {"sub": str(regular_id), "role": UserRole.USER.value}
    access_token = create_jwt_token(regular_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    mail_payload = {
        "subject": "Test Subject",
        "body": "Test Body Content"
    }

    with patch("bank_auth.clients.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.exists.return_value = False

        response = await ac.post(
            "/admin/mass-mail",
            json=mail_payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_mass_mail_unauthorized(ac: AsyncClient):
    mail_payload = {
        "subject": "Test Subject",
        "body": "Test Body Content"
    }
    response = await ac.post("/admin/mass-mail", json=mail_payload)
    assert response.status_code == status.HTTP_403_FORBIDDEN

# BAN USER

@pytest.mark.asyncio
async def test_ban_user_success(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_security",
            email="admin_sec@example.com",
            hashed_password="123",
            phone="+375297111111",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Security",
            is_active=True,
            role=UserRole.ADMIN,
        )
        target = UserTable(
            username="bad_user",
            email="bad@example.com",
            hashed_password="123",
            phone="+375297222222",
            birth_date=datetime.date(1995, 1, 1),
            first_name="Bad",
            last_name="User",
            is_active=True,
            role=UserRole.USER,
            is_banned=False,
        )
        session.add_all([admin, target])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(target)
        admin_id = admin.id
        target_id = target.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis, patch(
        "bank_auth.clients.kafka_producer", new_callable=AsyncMock
    ) as mock_kafka:
        mock_redis.exists.return_value = False

        response = await ac.patch(
            f"/admin/users/{target_id}/ban",
            json={"is_banned": True},
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert mock_kafka.send_and_wait.called

    async with TestingSessionLocal() as session:
        query = select(UserTable).where(UserTable.id == target_id)
        result = await session.execute(query)
        updated_user = result.scalar_one()
        assert updated_user.is_banned is True


@pytest.mark.asyncio
async def test_ban_user_forbidden_for_regular_user(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        regular = UserTable(
            username="hacker_wanna_be",
            email="hacker@example.com",
            hashed_password="123",
            phone="+375297333333",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Hacker",
            last_name="User",
            is_active=True,
            role=UserRole.USER,
        )
        session.add(regular)
        await session.commit()
        await session.refresh(regular)
        regular_id = regular.id

    regular_payload = {"sub": str(regular_id), "role": UserRole.USER.value}
    access_token = create_jwt_token(regular_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis:
        mock_redis.exists.return_value = False

        response = await ac.patch(
            f"/admin/users/{regular_id}/ban",
            json={"is_banned": True},
            headers=headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_login_banned_user_forbidden(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        banned_user = UserTable(
            username="banned_warrior",
            email="banned@example.com",
            hashed_password="123",
            phone="+375297444444",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Banned",
            last_name="User",
            is_active=True,
            is_banned=True,
        )
        from bank_auth.utils import hash_password

        banned_user.hashed_password = hash_password("password123")
        session.add(banned_user)
        await session.commit()

    login_payload = {
        "username_or_email": "banned_warrior",
        "password": "password123",
    }

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ), patch("bank_auth.clients.kafka_producer", new_callable=AsyncMock):
        response = await ac.post("/auth/login", json=login_payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "blocked due to security reasons" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ban_user_infrastructure_failure_rollback(ac: AsyncClient):
    async with TestingSessionLocal() as session:
        admin = UserTable(
            username="admin_security_fail",
            email="admin_fail@example.com",
            hashed_password="123",
            phone="+375297555555",
            birth_date=datetime.date(1990, 1, 1),
            first_name="Admin",
            last_name="Fail",
            is_active=True,
            role=UserRole.ADMIN,
        )
        target = UserTable(
            username="target_user_ban_rollback",
            email="target_ban_rollback@example.com",
            hashed_password="123",
            phone="+375297666666",
            birth_date=datetime.date(1995, 1, 1),
            first_name="Target",
            last_name="BanRollback",
            is_active=True,
            role=UserRole.USER,
            is_banned=False,
        )
        session.add_all([admin, target])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(target)
        admin_id = admin.id
        target_id = target.id

    admin_payload = {"sub": str(admin_id), "role": UserRole.ADMIN.value}
    access_token = create_jwt_token(admin_payload, datetime.timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "bank_auth.clients.redis_client", new_callable=AsyncMock
    ) as mock_redis, patch(
        "bank_auth.clients.kafka_producer", new_callable=AsyncMock
    ) as mock_kafka:
        mock_redis.exists.return_value = False
        mock_kafka.send_and_wait.side_effect = Exception("Kafka connection lost")

        response = await ac.patch(
            f"/admin/users/{target_id}/ban",
            json={"is_banned": True},
            headers=headers,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    async with TestingSessionLocal() as session:
        query = select(UserTable).where(UserTable.id == target_id)
        result = await session.execute(query)
        rolled_back_user = result.scalar_one()
        assert rolled_back_user.is_banned is False