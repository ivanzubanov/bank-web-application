import os
from functools import cached_property, cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTS_DIR = os.path.join(BASE_DIR, "certs")

class Settings(BaseSettings):
    AUTH_DB_USER: str
    AUTH_DB_PASSWORD: str
    AUTH_DB_NAME: str

    AUTH_DB_HOST: str = "localhost"
    AUTH_DB_PORT: int = 54311

    REDIS_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @cached_property
    def private_key(self) -> str:
        with open(os.path.join(CERTS_DIR, "private_key.pem"), "r") as f:
            return f.read()

    @cached_property
    def public_key(self) -> str:
        with open(os.path.join(CERTS_DIR, "public_key.pem"), "r") as f:
            return f.read()

settings = Settings()