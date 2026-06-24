from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    WALLET_DB_USER: str
    WALLET_DB_PASSWORD: str
    WALLET_DB_NAME: str

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8"
    )

settings = Settings()