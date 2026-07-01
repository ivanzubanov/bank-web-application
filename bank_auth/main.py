import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from redis.asyncio import from_url
from aiokafka import AIOKafkaProducer

from bank_auth import clients
from bank_auth.router import router
from bank_auth.admin_router import admin_router
from bank_auth.config import settings

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing Redis & Kafka connection...")
    clients.redis_client = from_url(
        settings.REDIS_URL,
        decode_responses=True
    )
    await clients.redis_client.ping()

    clients.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
    )
    await clients.kafka_producer.start()
    logging.info("Infrastructure clients have been successfully launched.")

    yield

    logging.info("Closing connections...")
    if clients.redis_client:
        await clients.redis_client.close()
    if clients.kafka_producer:
        await clients.kafka_producer.stop()
    logging.info("The 'bank_auth' application has been successfully stopped.")

app = FastAPI(title="Bank Authentication Service", lifespan=lifespan)
app.include_router(router)
app.include_router(admin_router)