"""Centralized, type-safe configuration (spec §4.1).

Replaces scattered ``os.getenv`` calls with a single pydantic-settings model.
- Type-checked at **startup** (fail fast instead of failing deep in a request).
- ``SecretStr`` keeps the API key out of logs / ``repr``.
- Backward compatible with the existing ``.env`` (separate ``DATABASE_*`` vars)
  while also supporting the spec-style single ``DATABASE_URL``.
"""

from __future__ import annotations

from pydantic import Field, HttpUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM (SiliconFlow) ---
    silicon_flow_api_key: SecretStr = Field(..., alias="SILICON_FLOW_API_KEY")
    silicon_flow_base_url: HttpUrl = Field(
        "https://api.siliconflow.cn/v1", alias="SILICON_FLOW_BASE_URL"
    )
    nl2sql_model: str = Field("Qwen/Qwen2.5-Coder-32B-Instruct", alias="SILICON_FLOW_NL2SQL_MODEL")
    reasoning_model: str = Field("deepseek-ai/DeepSeek-V3", alias="SILICON_FLOW_REASONING_MODEL")
    helper_model: str = Field("Qwen/Qwen2.5-32B-Instruct", alias="SILICON_FLOW_HELPER_MODEL")
    judge_model: str = Field("deepseek-ai/deepseek-chat")

    # --- Embedding / Rerank ---
    embedding_model: str = Field("BAAI/bge-large-zh-v1.5", alias="SILICON_FLOW_EMBEDDING_MODEL")
    embedding_device: str = "cpu"
    reranker_model: str = Field("BAAI/bge-reranker-v2-m3", alias="SILICON_FLOW_RERANK_MODEL")

    # --- Database (support both DATABASE_URL and the 5 separate vars) ---
    database_url: PostgresDsn | None = Field(None, alias="DATABASE_URL")
    database_user: str | None = Field(None, alias="DATABASE_USER")
    database_password: str | None = Field(None, alias="DATABASE_PASSWORD")
    database_host: str | None = Field(None, alias="DATABASE_HOST")
    database_port: int | None = Field(None, alias="DATABASE_PORT")
    database_name: str | None = Field(None, alias="DATABASE_NAME")

    # --- RAG ---
    vector_store_type: str = "faiss"  # faiss | pgvector | milvus
    rag_top_k: int = 5

    # --- Agent ---
    max_react_steps: int = 10
    enable_reflection: bool = True

    # --- Observability (optional) ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: HttpUrl | None = None

    @property
    def sqlalchemy_url(self) -> str:
        """Build a SQLAlchemy-compatible URL from either DATABASE_URL or parts.

        Why: the spec prefers a single ``DATABASE_URL`` while the legacy ``.env``
        splits it into 5 vars. Supporting both keeps the existing app working.
        """
        if self.database_url is not None:
            return str(self.database_url)
        missing = [
            name
            for name, val in (
                ("DATABASE_USER", self.database_user),
                ("DATABASE_PASSWORD", self.database_password),
                ("DATABASE_HOST", self.database_host),
                ("DATABASE_PORT", self.database_port),
                ("DATABASE_NAME", self.database_name),
            )
            if val is None
        ]
        if not missing:
            return (
                f"postgresql://{self.database_user}:{self.database_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        raise ValueError("Missing DB config: set DATABASE_URL or all of " + ", ".join(missing))


# Module-level singleton so other modules can do: from app.config import settings
try:
    settings = Settings()
except Exception:  # pragma: no cover - depends on environment at import time
    settings = None  # type: ignore[assignment]
