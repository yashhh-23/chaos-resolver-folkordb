"""Embeddings service supporting local deterministic embeddings and remote providers (OpenAI)."""

import os
import math
import hashlib
from typing import List, Optional
from src.config import settings
from src.utils.logger import logger


class EmbeddingService:
    """Computes normalized dense vector representations for nodes."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.openai_client = None

        if settings.openai_api_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
                logger.info("EmbeddingService: OpenAI client initialized.")
            except Exception as e:
                logger.warning(f"EmbeddingService: Could not initialize OpenAI client ({e}), using local engine.")

    def embed_text(self, text: str) -> List[float]:
        """Embeds a single string into a normalized float vector."""
        if self.openai_client:
            try:
                res = self.openai_client.embeddings.create(
                    input=text,
                    model="text-embedding-3-small",
                )
                raw_vec = res.data[0].embedding
                # If dimension mismatch, truncate or project
                if len(raw_vec) >= self.dimension:
                    vec = raw_vec[:self.dimension]
                else:
                    vec = raw_vec + [0.0] * (self.dimension - len(raw_vec))
                return self._normalize(vec)
            except Exception as e:
                logger.warning(f"OpenAI embedding call failed: {e}. Falling back to local semantic embedder.")

        return self._local_semantic_embed(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embeds a batch of texts."""
        return [self.embed_text(t) for t in texts]

    def _local_semantic_embed(self, text: str) -> List[float]:
        """Fast, robust, deterministic semantic embedding generator for local operation.

        Uses hash-based n-gram feature hashing combined with semantic anchor projection
        to generate normalized dense vectors where semantically overlapping texts
        have high cosine similarity.
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
