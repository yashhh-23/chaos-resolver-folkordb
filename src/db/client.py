"""FalkorDB Client Connection Manager supporting local Docker and FalkorDB Cloud."""

from typing import Optional, List, Dict, Any
import falkordb
from src.config import settings
from src.utils.logger import logger
from src.schema.cypher_schema import INDEX_QUERIES, sanitize_cypher_query


class FalkorDBClient:
    """Singleton-style wrapper for FalkorDB connections."""

    _instance: Optional["FalkorDBClient"] = None

    def __init__(self):
        self._db: Optional[falkordb.FalkorDB] = None
        self._connected = False

    @classmethod
    def get_instance(cls) -> "FalkorDBClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def connect(self) -> falkordb.FalkorDB:
        """Establishes or returns the existing FalkorDB connection."""
        if self._db is not None and self._connected:
            try:
                # Active connection liveness check to prevent stale connection reuse
                _ = self._db.list_graphs()
                return self._db
            except Exception as e:
                logger.warning(f"Cached FalkorDB connection was lost ({e}), reconnecting...")
                self._connected = False
                self._db = None

        try:
            if settings.falkordb_url:
                logger.info("Connecting to FalkorDB using connection URL...")
                self._db = falkordb.FalkorDB.from_url(settings.falkordb_url)
            else:
                logger.info(
                    f"Connecting to FalkorDB at {settings.falkordb_host}:{settings.falkordb_port} "
                    f"(ssl={settings.falkordb_ssl})..."
                )
                self._db = falkordb.FalkorDB(
                    host=settings.falkordb_host,
                    port=settings.falkordb_port,
                    username=settings.falkordb_username,
                    password=settings.falkordb_password,
                    ssl=settings.falkordb_ssl,
                )

            # Test connection with list_graphs or ping
            _ = self._db.list_graphs()
            self._connected = True
            logger.info("Successfully connected to FalkorDB.")
            return self._db
        except Exception as e:
            self._connected = False
            self._db = None
            logger.warning(
                f"Could not connect to FalkorDB: {e}. "
                "Ensure local Docker container ('docker-compose up -d') or FalkorDB Cloud instance is active."
            )
            raise e

    def is_connected(self) -> bool:
        """Checks if FalkorDB is currently reachable."""
        try:
            if self._db is None or not self._connected:
                self.connect()
            else:
                _ = self._db.list_graphs()
            return True
        except Exception:
            self._connected = False
            self._db = None
            return False

    def get_graph(self, graph_name: str) -> falkordb.Graph:
        """Retrieves a specific graph handle for multigraph isolation."""
        db = self.connect()
        return db.select_graph(graph_name)

    def apply_schema_indexes(self, graph_name: str) -> List[str]:
        """Applies schema index queries to optimize lookups and enforce uniqueness."""
        graph = self.get_graph(graph_name)
        results = []
        for query in INDEX_QUERIES:
            try:
                graph.query(query)
                results.append(f"SUCCESS: {query}")
                logger.debug(f"[{graph_name}] Index created: {query}")
            except Exception as e:
                # If index already exists, FalkorDB may raise an error, which is safe to ignore
                results.append(f"INFO: {query} ({e})")
        return results

    def query(self, graph_name: str, query: str, params: Optional[Dict[str, Any]] = None, sanitize: bool = True):
        """Executes a Cypher query with optional query sanitization."""
        if sanitize:
            query = sanitize_cypher_query(query)
        graph = self.get_graph(graph_name)
        return graph.query(query, params)


db_client = FalkorDBClient.get_instance()
