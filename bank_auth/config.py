from pydantic_settings import BaseSettings, SettingsConfigDict

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

settings = Settings()