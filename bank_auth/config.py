from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    AUTH_DB_USER: str
    AUTH_DB_PASSWORD: str
    AUTH_DB_NAME: str

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8"
    )

settings = Settings()