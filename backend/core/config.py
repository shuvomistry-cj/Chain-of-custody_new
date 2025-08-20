import os
import base64
from typing import Optional
from pydantic_settings import BaseSettings


from pydantic_settings import BaseSettings, SettingsConfigDict
# ...

class Settings(BaseSettings):
    app_name: str = "CoC Evidence MVP"
    secret_key: str
    jwt_alg: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 43200
    app_aes_key_base64: str
    database_url: str = "sqlite:///./coc.db"

    # File upload settings
    max_file_size: int = 25 * 1024 * 1024  # 25MB
    allowed_mime_types: list[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain"
    ]

    # Pydantic v2 settings
    model_config = SettingsConfigDict(env_file=".env")

    @property
    def aes_key(self) -> bytes:
        """Decode the base64 AES key to bytes"""
        return base64.b64decode(self.app_aes_key_base64)


settings = Settings()