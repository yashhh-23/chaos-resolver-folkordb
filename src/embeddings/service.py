"""Embeddings service supporting local deterministic embeddings and remote providers (OpenAI)."""

import math
import hashlib
from typing import List
from src.config import settings
from src.utils.logger import logger


class EmbeddingService:
    """Computes normalized dense vector representations for nodes."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.openai_client = None
        self.provider = "local_hash_anchor"
        self.model_name = "deterministic-hash-anchor-v1"
        self.model_version = f"local:deterministic-anchor:dim={dimension}:v1"
        self.is_trained_model = False

        if settings.openai_api_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
                self.provider = "openai"
                self.model_name = "text-embedding-3-small"
                self.model_version = f"openai:text-embedding-3-small:dim={dimension}"
                self.is_trained_model = True
                logger.info(f"EmbeddingService: OpenAI client initialized with model '{self.model_name}' (dim={self.dimension}).")
            except Exception as e:
                logger.warning(f"EmbeddingService: Could not initialize OpenAI client ({e}), using local deterministic engine.")

    def embed_text(self, text: str) -> List[float]:
        """Embeds a single string into a normalized float vector.

        When OpenAI is configured, uses text-embedding-3-small with native Matryoshka
        dimensionality reduction (dimensions=self.dimension).
        When offline or OpenAI is unconfigured, uses the local deterministic semantic anchor
        baseline engine, clearly labeled as a non-trained deterministic fallback.
        """
        if self.openai_client:
            try:
                # Use OpenAI's native Matryoshka Representation Learning (MRL) dimension parameter
                res = self.openai_client.embeddings.create(
                    input=text,
                    model=self.model_name,
                    dimensions=self.dimension,
                )
                vec = res.data[0].embedding
                return self._normalize(vec)
            except Exception as e:
                logger.warning(f"OpenAI embedding call failed: {e}. Falling back to local semantic embedder.")

        return self._local_semantic_embed(text)

    def _local_semantic_embed(self, text: str) -> List[float]:
        """Fast, robust, deterministic semantic embedding baseline for offline/local operation.

        NOTE: This is a deterministic heuristic baseline utilizing SHA256/MD5 n-gram hashing
        and domain anchor projection for zero-dependency operation. It should NOT be presented
        as equivalent to a trained deep neural embedding model (e.g. text-embedding-3-small).
        """
        cleaned = text.lower().strip()
        tokens = [t.strip(".,;:?!'\"()[]{}") for t in cleaned.split()]

        # Domain concept seeds for semantic clustering
        concept_anchors = {
            "auth": ["oauth2", "jwt", "session", "token", "login", "identity", "authentication", "pulse", "gatekeeper", "credential"],
            "ledger": ["ledger", "double-entry", "settlement", "stripe", "payout", "balance", "reconciliation", "transaction", "vault-engine"],
            "kyc": ["kyc", "onboarding", "uidai", "aadhaar", "verification", "biometric", "identity-check"],
            "retention": ["retention", "purge", "audit", "logs", "180", "30", "storage", "telemetry", "forensic"],
            "network": ["mtls", "spiffe", "envoy", "istio", "mesh", "bearer", "api-key", "tls", "https"],
        }

        vec = [0.0] * self.dimension

        # 1. Project tokens into vector space via n-gram hashing
        for i, token in enumerate(tokens):
            if not token:
                continue
            # Hash to index
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h // self.dimension) % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 / (1.0 + 0.05 * i))

            # Character 3-grams for morphology
            for j in range(max(0, len(token) - 2)):
                tri = token[j:j+3]
                h_tri = int(hashlib.md5(tri.encode("utf-8")).hexdigest(), 16)
                idx_tri = h_tri % self.dimension
                vec[idx_tri] += 0.3 * (1.0 if h_tri % 2 == 0 else -1.0)

        # 2. Add domain semantic anchor biases so matching concepts align closely
        for anchor_idx, (domain, keywords) in enumerate(concept_anchors.items()):
            matches = sum(1 for kw in keywords if kw in cleaned)
            if matches > 0:
                base_slot = (anchor_idx * 40) % self.dimension
                for offset in range(30):
                    slot = (base_slot + offset) % self.dimension
                    vec[slot] += (matches * 1.5)

        return self._normalize(vec)

    @staticmethod
    def _normalize(vec: List[float]) -> List[float]:
        """L2-normalizes a vector."""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [round(x / norm, 6) for x in vec]

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Computes cosine similarity between two unit vectors."""
        if len(v1) != len(v2):
            raise ValueError(f"Vector dimensions do not match: {len(v1)} vs {len(v2)}")
        dot = sum(a * b for a, b in zip(v1, v2))
        return max(-1.0, min(1.0, dot))


embedding_service = EmbeddingService(dimension=384)
