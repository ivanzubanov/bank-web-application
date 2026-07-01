import asyncio
import json
from json import JSONDecodeError
import logging
import aiosmtplib
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from redis.asyncio import Redis
from pydantic import ValidationError

from bank_notify.config import settings
from bank_notify.services.email import (
    send_email,
    render_verification_template,
    render_mass_mail_template
)
from bank_notify.kafka_schemas import EmailVerificationEvent, AdminMassMailEvent

logger = logging.getLogger("bank_notify_worker")


async def run_worker_loop():
    consumer = AIOKafkaConsumer(
        "email_verification",
        "admin_mass_mail",
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_NOTIFICATION_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest"
    )

    dlq_producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    await consumer.start()
    await dlq_producer.start()

    logger.info("Worker services (Kafka Consumer, DLQ Producer, Redis) initialized.")

    try:
        async for msg in consumer:
            logger.info(f"Received message from topic: {msg.topic}")
            lock_key = None
            dlq_topic = f"{msg.topic}_dlq"

            try:
                try:
                    payload = json.loads(msg.value.decode("utf-8"))
                except JSONDecodeError as json_exc:
                    logger.error(f"Poison pill (Raw JSON Error) in topic {msg.topic}: {json_exc}. Routing to {dlq_topic}")
                    await dlq_producer.send_and_wait(
                        topic=dlq_topic,
                        value=msg.value,
                        headers=[("error_reason", b"Invalid JSON syntax")]
                    )
                    await consumer.commit()
                    continue

                try:
                    if msg.topic == "email_verification":
                        event = EmailVerificationEvent(**payload)
                        html = render_verification_template(username=event.username, code=event.otp_code)
                        subject = "Registration confirmation"
                    elif msg.topic == "admin_mass_mail":
                        event = AdminMassMailEvent(**payload)
                        html = render_mass_mail_template(username=event.username, text=event.body)
                        subject = event.subject
                    else:
                        raise ValueError(f"Unsupported topic received: {msg.topic}")

                    event_id = event.event_id
                    target_email = event.email

                except (ValidationError, ValueError) as val_exc:
                    logger.error(f"Structural defect (Validation Error) in topic {msg.topic}: {val_exc}. Routing to {dlq_topic}")
                    await dlq_producer.send_and_wait(
                        topic=dlq_topic,
                        value=msg.value,
                        headers=[("error_reason", str(val_exc).encode("utf-8"))]
                    )
                    await consumer.commit()
                    continue

                lock_key = f"notification:{event_id}"
                is_new_event = await redis_client.set(lock_key, "PROCESSING", nx=True, ex=900)

                if not is_new_event:
                    logger.warning(f"Duplicate event ignored or already processing: {event_id}")
                    await consumer.commit()
                    continue

                await send_email(
                    to_email=target_email,
                    subject=subject,
                    html_content=html
                )

                await redis_client.set(lock_key, "SUCCESS", ex=86400)
                logger.info(f"Notification for event {event_id} sent successfully.")
                await consumer.commit()

            except (aiosmtplib.SMTPException, OSError, asyncio.TimeoutError) as infra_exc:
                logger.critical(f"Infrastructure error. Releasing lock and crashing worker. Reason: {infra_exc}")
                if lock_key:
                    await redis_client.delete(lock_key)
                raise infra_exc

    except asyncio.CancelledError:
        logger.info("Worker task received cancellation signal.")
        raise
    finally:
        logger.info("Closing all background connections...")
        await consumer.stop()
        await dlq_producer.stop()
        await redis_client.close()
        logger.info("Worker context closed cleanly.")