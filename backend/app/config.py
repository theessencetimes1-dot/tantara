"""Environment configuration; local providers are the default."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

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
    local_llm_timeout: float = Field(
        default=20.0, validation_alias="TANTARA_LOCAL_LLM_TIMEOUT", gt=0, le=29.0
    )
    local_llm_model: str = "MiniCPM5-2B"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    embedding_provider: str = "fastembed"
    fastembed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-3.5"
    embedding_dimensions: int = 384
    # faiss | postgres | auto (auto: postgres when the workspace database is PostgreSQL)
    vector_backend: str = Field(
        default="auto", validation_alias=AliasChoices("VECTOR_BACKEND", "TANTARA_VECTOR_BACKEND")
    )
    # filesystem | s3 (S3-compatible object storage such as MinIO) | supabase
    object_storage: str = Field(
        default="filesystem", validation_alias=AliasChoices("OBJECT_STORAGE", "TANTARA_OBJECT_STORAGE")
    )
    s3_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("S3_ENDPOINT", "MINIO_ENDPOINT", "OBJECT_STORAGE_ENDPOINT"),
    )
    s3_bucket: str = Field(default="tantara", validation_alias=AliasChoices("S3_BUCKET", "MINIO_BUCKET"))
    s3_access_key: str = Field(default="", validation_alias=AliasChoices("S3_ACCESS_KEY", "MINIO_ACCESS_KEY"))
    s3_secret_key: str = Field(default="", validation_alias=AliasChoices("S3_SECRET_KEY", "MINIO_SECRET_KEY"))
    s3_region: str = Field(default="us-east-1", validation_alias=AliasChoices("S3_REGION", "MINIO_REGION"))
    s3_secure: bool = Field(default=False, validation_alias=AliasChoices("S3_SECURE", "MINIO_SECURE"))
    # Server-side pool tuning (PostgreSQL workspaces).
    db_pool_size: int = Field(
        default=5, validation_alias=AliasChoices("DB_POOL_SIZE", "TANTARA_DB_POOL_SIZE")
    )
    db_pool_max_overflow: int = Field(
        default=10, validation_alias=AliasChoices("DB_POOL_MAX_OVERFLOW", "TANTARA_DB_POOL_MAX_OVERFLOW")
    )
    db_pool_recycle: int = Field(
        default=1800, validation_alias=AliasChoices("DB_POOL_RECYCLE", "TANTARA_DB_POOL_RECYCLE")
    )
    analytics_backend: str = "none"
    enable_cloud_providers: bool = False
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = Field(
        default="tantara-documents",
        validation_alias=AliasChoices("SUPABASE_STORAGE_BUCKET", "SUPABASE_BUCKET"),
    )
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
        if self.object_storage == "s3" and not (
            self.s3_endpoint and self.s3_access_key and self.s3_secret_key
        ):
            raise ValueError(
                "OBJECT_STORAGE=s3 requires S3_ENDPOINT, S3_ACCESS_KEY and S3_SECRET_KEY "
                "(MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY are accepted aliases)"
            )
        if self.object_storage == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key and self.supabase_storage_bucket
        ):
            raise ValueError(
                "OBJECT_STORAGE=supabase requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY "
                "and SUPABASE_STORAGE_BUCKET"
            )
        if self.object_storage not in {"filesystem", "s3", "supabase"}:
            raise ValueError("OBJECT_STORAGE must be one of: filesystem, s3, supabase")
        if self.vector_backend not in {"auto", "faiss", "postgres"}:
            raise ValueError("VECTOR_BACKEND must be one of: auto, faiss, postgres")
        return self

    @property
    def database_dialect(self) -> str:
        """`sqlite` or `postgresql` — the dialect the workspace database actually uses."""
        return make_url(self.database_url or "").get_backend_name()

    @property
    def effective_vector_backend(self) -> str:
        """`postgres` keeps vectors inside the database; `faiss` keeps the local persistent index."""
        if self.vector_backend != "auto":
            if self.vector_backend == "postgres" and self.database_dialect != "postgresql":
                raise ValueError("VECTOR_BACKEND=postgres requires a PostgreSQL DATABASE_URL")
            return self.vector_backend
        return "postgres" if self.database_dialect == "postgresql" else "faiss"

    @property
    def object_storage_backend(self) -> str:
        if self.object_storage == "s3":
            return "s3"
        return "supabase" if self.object_storage == "supabase" else "filesystem"


@lru_cache
def get_settings() -> Settings:
    return Settings()
