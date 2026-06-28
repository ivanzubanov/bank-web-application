import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
async def test_successful_registration(ac: AsyncClient):
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

    # Redis & Kafka isolation
    with patch("services.clients.redis_client", new_callable=AsyncMock) as mock_redis, \
            patch("services.clients.kafka_producer", new_callable=AsyncMock) as mock_kafka:
        response = await ac.post("/auth/register", json=user_payload)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == user_payload["username"]
        assert data["is_active"] is False
        assert "id" in data

        assert mock_redis.set.called
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