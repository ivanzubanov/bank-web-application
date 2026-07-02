import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, ANY
import aiosmtplib

from bank_notify.worker import run_worker_loop


class MockKafkaMessage:
    def __init__(self, topic, value, headers=None):
        self.topic = topic
        self.value = value
        self.headers = headers or []


@pytest.fixture
def mock_infra():
    with patch("bank_notify.worker.AIOKafkaConsumer") as mock_consumer_cls, \
            patch("bank_notify.worker.AIOKafkaProducer") as mock_producer_cls, \
            patch("bank_notify.worker.Redis") as mock_redis_cls, \
            patch("bank_notify.worker.send_email") as mock_send_email:
        mock_consumer = mock_consumer_cls.return_value
        mock_producer = mock_producer_cls.return_value
        mock_redis = mock_redis_cls.from_url.return_value

        mock_consumer.start = AsyncMock()
        mock_consumer.commit = AsyncMock()
        mock_consumer.stop = AsyncMock()

        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()

        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        yield {
            "consumer": mock_consumer,
            "producer": mock_producer,
            "redis": mock_redis,
            "send_email": mock_send_email
        }


def setup_kafka_stream(mock_consumer, message):
    async def mock_async_iter(*args, **kwargs):
        yield message
        raise asyncio.CancelledError()

    mock_consumer.__aiter__ = mock_async_iter


@pytest.mark.asyncio
async def test_worker_email_verification_success(mock_infra):
    infra = mock_infra

    payload = {
        "event_id": "verify_evt_123",
        "email": "warrior@example.com",
        "otp_code": "987654",
        "username": "test_warrior"
    }
    mock_msg = MockKafkaMessage("email_verification", json.dumps(payload).encode("utf-8"))
    setup_kafka_stream(infra["consumer"], mock_msg)

    with pytest.raises(asyncio.CancelledError):
        await run_worker_loop()

    infra["consumer"].start.assert_called_once()
    infra["producer"].start.assert_called_once()
    infra["redis"].set.assert_any_call("notification:verify_evt_123", "PROCESSING", nx=True, ex=900)
    infra["send_email"].assert_called_once_with(
        to_email="warrior@example.com",
        subject="Registration confirmation",
        html_content=ANY
    )
    infra["redis"].set.assert_any_call("notification:verify_evt_123", "SUCCESS", ex=86400)
    infra["consumer"].commit.assert_called_once()


@pytest.mark.asyncio
async def test_worker_admin_mass_mail_success(mock_infra):
    infra = mock_infra

    payload = {
        "event_id": "mass_mail_777",
        "email": "user@example.com",
        "username": "lucky_user",
        "subject": "System Upgrade",
        "body": "We are upgrading our servers.",
        "dispatched_at": "2026-07-02T12:00:00"
    }
    mock_msg = MockKafkaMessage("admin_mass_mail", json.dumps(payload).encode("utf-8"))
    setup_kafka_stream(infra["consumer"], mock_msg)

    with pytest.raises(asyncio.CancelledError):
        await run_worker_loop()

    infra["send_email"].assert_called_once_with(
        to_email="user@example.com",
        subject="System Upgrade",
        html_content=ANY
    )
    infra["redis"].set.assert_any_call("notification:mass_mail_777", "SUCCESS", ex=86400)
    infra["consumer"].commit.assert_called_once()


@pytest.mark.asyncio
async def test_worker_duplicate_event_idempotency(mock_infra):
    infra = mock_infra
    infra["redis"].set.return_value = False

    payload = {
        "event_id": "duplicate_id",
        "email": "warrior@example.com",
        "otp_code": "111111",
        "username": "test"
    }
    mock_msg = MockKafkaMessage("email_verification", json.dumps(payload).encode("utf-8"))
    setup_kafka_stream(infra["consumer"], mock_msg)

    with pytest.raises(asyncio.CancelledError):
        await run_worker_loop()

    infra["send_email"].assert_not_called()
    infra["consumer"].commit.assert_called_once()


@pytest.mark.asyncio
async def test_worker_poison_pill_routing_to_dlq(mock_infra):
    infra = mock_infra

    broken_payload = b"invalid-raw-json-format{"
    mock_msg = MockKafkaMessage("email_verification", broken_payload)
    setup_kafka_stream(infra["consumer"], mock_msg)

    with pytest.raises(asyncio.CancelledError):
        await run_worker_loop()

    infra["producer"].send_and_wait.assert_called_once_with(
        topic="email_verification_dlq",
        value=broken_payload,
        headers=[("error_reason", b"Invalid JSON syntax")]
    )
    infra["consumer"].commit.assert_called_once()
    infra["send_email"].assert_not_called()


@pytest.mark.asyncio
async def test_worker_validation_error_routing_to_dlq(mock_infra):
    infra = mock_infra

    invalid_payload = {"event_id": "bad_schema_123", "username": "scammer"}
    raw_bytes = json.dumps(invalid_payload).encode("utf-8")
    mock_msg = MockKafkaMessage("email_verification", raw_bytes)
    setup_kafka_stream(infra["consumer"], mock_msg)

    with pytest.raises(asyncio.CancelledError):
        await run_worker_loop()

    infra["producer"].send_and_wait.assert_called_once_with(
        topic="email_verification_dlq",
        value=raw_bytes,
        headers=ANY
    )
    infra["consumer"].commit.assert_called_once()
    infra["send_email"].assert_not_called()


@pytest.mark.asyncio
async def test_worker_infrastructure_failure_rollback_lock(mock_infra):
    infra = mock_infra
    infra["send_email"].side_effect = aiosmtplib.SMTPException("Connection timed out")

    payload = {
        "event_id": "infra_fail_999",
        "email": "target@example.com",
        "otp_code": "000000",
        "username": "unlucky"
    }
    mock_msg = MockKafkaMessage("email_verification", json.dumps(payload).encode("utf-8"))

    async def mock_async_iter(*args, **kwargs):
        yield mock_msg

    infra["consumer"].__aiter__ = mock_async_iter

    with pytest.raises(aiosmtplib.SMTPException):
        await run_worker_loop()

    infra["redis"].delete.assert_called_once_with("notification:infra_fail_999")
    infra["consumer"].commit.assert_not_called()