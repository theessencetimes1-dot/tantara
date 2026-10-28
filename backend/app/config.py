"""Environment configuration; local providers are the default."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORS_ORIGINS = ",".join(
    [
        *(f"http://localhost:{port}" for port in range(3000, 3021)),
        *(f"http://127.0.0.1:{port}" for port in range(3000, 3021)),
    ]
)


class Settings(BaseSettings):
    database_url: str | None = None
    data_dir: Path = Field(
        default=ROOT / "data", validation_alias=AliasChoices("TANTARA_DATA_DIR", "DATA_DIR")
    )
    workspace_time_zone: str = Field(default="Asia/Kolkata", validation_alias="TANTARA_WORKSPACE_TIME_ZONE")
    ai_provider: str = "local"
    local_llm_base_url: str = Field(
        default="http://192.168.0.101:8080/v1",
        validation_alias=AliasChoices("TANTARA_LOCAL_LLM_BASE_URL", "LOCAL_LLM_BASE_URL"),
    )
    local_llm_model: str = "MiniCPM5-2B"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    embedding_provider: str = "fastembed"
    fastembed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-3.5"
    embedding_dimensions: int = 384
    vector_backend: str = "faiss"
    analytics_backend: str = "none"
    enable_cloud_providers: bool = False
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    max_upload_mb: int = 25
    chunk_size_chars: int = 1800
    chunk_overlap_chars: int = 250
    default_top_k: int = 5
    tantara_admin_password: str = "tantara-local"
    cors_origins: str = Field(
        default=DEFAULT_CORS_ORIGINS,
        validation_alias=AliasChoices("CORS_ORIGINS", "TANTARA_CORS_ORIGINS"),
    )
    model_config = SettingsConfigDict(
        env_file=(str(ROOT / ".env"), str(ROOT / "env_example")), extra="ignore"
    )

    @model_validator(mode="after")
    def resolve_workspace_paths(self):
        self.data_dir = self.data_dir.expanduser().resolve()
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'tantara.db'}"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
