import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTS_DIR = os.path.join(BASE_DIR, "certs")

class Settings(BaseSettings):
    AUTH_DB_USER: str
    AUTH_DB_PASSWORD: str
    AUTH_DB_NAME: str

    REDIS_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def private_key(self) -> str:
        with open(os.path.join(CERTS_DIR, "private_key.pem"), "r") as f:
            return f.read()

    @property
    def public_key(self) -> str:
        with open(os.path.join(CERTS_DIR, "public_key.pem"), "r") as f:
            return f.read()

settings = Settings()