from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for FalkorDB connection and graph names."""

    # FalkorDB Connection
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_username: Optional[str] = None
    falkordb_password: Optional[str] = None
    falkordb_ssl: bool = False
    falkordb_url: Optional[str] = None

    # Multigraph Tenancy
    graph_finpay: str = "finpay_graph"
    graph_vaultly: str = "vaultly_graph"
    graph_merged: str = "merged_brain"

    # LLM Settings (for Phase 2 & 3)
    openai_api_key: Optional[str] = None

    # General
    environment: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
