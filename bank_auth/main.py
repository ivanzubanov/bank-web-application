import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import clients
from router import router
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from redis.asyncio import from_url
from aiokafka import AIOKafkaProducer

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Redis & Kafka connection...")
    clients.redis_client = from_url(
        settings.REDIS_URL,
        decode_responses=True
    )
    await clients.redis_client.ping()

    clients.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
    )

    await clients.kafka_producer.start()
    print("Infrastructure clients have been successfully launched.")

    yield

    print("Closing connections...")
    if clients.redis_client:
        await clients.redis_client.close()

    if clients.kafka_producer:
        await clients.kafka_producer.stop()

    print("The 'bank_auth' application has been successfully stopped.")

app = FastAPI(title="Bank Authentication Service", lifespan=lifespan)

app.include_router(router)