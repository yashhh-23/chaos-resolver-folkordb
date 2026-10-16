from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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

    # LLM Settings (for Phase 2 & 3: Groq Llama-3.3-70B / OpenAI)
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    llm_model: str = "llama-3.3-70b-versatile"

    # Auto-Linker Engine Parameters
    auto_linker_threshold: float = 0.82
    auto_linker_graph_bonus_per_api: float = 0.12
    auto_linker_domain_bonus: float = 0.05
    auto_linker_max_score: float = 0.99

    # General
    environment: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
