import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    sqlite_path: str = Field(default="/data/pcd.sqlite3", validation_alias="SQLITE_PATH")

    minio_endpoint: str = Field(default="minio:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", validation_alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="minioadmin", validation_alias="MINIO_ROOT_PASSWORD")
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")
    minio_bucket: str = Field(default="pcd", validation_alias="MINIO_BUCKET")
    public_minio_url: str | None = Field(default=None, validation_alias="PUBLIC_MINIO_URL")

    @field_validator("minio_secure", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in {"1", "true", "yes", "on"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


