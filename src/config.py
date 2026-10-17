from pathlib import Path
from typing import Optional
from pydantic import field_validator
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

    # Graph Traversal & Clustering Parameters
    warm_intro_max_directed_hops: int = 5
    warm_intro_max_bidirectional_hops: int = 4
    silos_subgraph_max_nodes: int = 25

    # Security & API Authorization
    api_key: str = "orgbridge-war-room-2026"
    admin_api_key: str = "orgbridge-admin-war-room-2026"
    cors_allowed_origins: str = (
        "https://falkordb-powered-resolver.vercel.app,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000"
    )

    # General
    environment: str = "development"
    log_level: str = "INFO"

    @field_validator(
        "groq_api_key",
        "openai_api_key",
        "falkordb_host",
        "falkordb_password",
        "api_key",
        "admin_api_key",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            return v_stripped if v_stripped else None
        return v

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
