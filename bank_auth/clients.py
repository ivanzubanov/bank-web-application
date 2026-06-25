from typing import Optional
from aiokafka import AIOKafkaProducer
from redis.asyncio import Redis

redis_client: Optional[Redis] = None
kafka_producer: Optional[AIOKafkaProducer] = None