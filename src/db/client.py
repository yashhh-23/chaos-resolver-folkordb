"""FalkorDB Client Connection Manager supporting local Docker and FalkorDB Cloud."""

import threading
import time
from typing import Optional, List, Dict, Any
import falkordb
from src.config import settings
from src.utils.logger import logger
from src.schema.cypher_schema import sanitize_cypher_query


class FalkorDBClient:
    """Singleton-style wrapper for FalkorDB connections with thread-safety and transient retry."""

    _instance: Optional["FalkorDBClient"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._db: Optional[falkordb.FalkorDB] = None
        self._connected = False
        self._conn_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "FalkorDBClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def connect(self) -> falkordb.FalkorDB:
        """Establishes or returns the existing FalkorDB connection in a thread-safe manner."""
        with self._conn_lock:
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
            with self._conn_lock:
                self._connected = False
                self._db = None
            return False

    def get_graph(self, graph_name: str) -> falkordb.Graph:
        """Retrieves a specific graph handle for multigraph isolation."""
        db = self.connect()
        return db.select_graph(graph_name)

    def query(
        self,
        graph_name: str,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        sanitize: bool = True,
        max_retries: int = 2,
    ):
        """Executes a Cypher query with optional query sanitization and transient retry."""
        if sanitize:
            query = sanitize_cypher_query(query)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                graph = self.get_graph(graph_name)
                return graph.query(query, params)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_connection_err = any(
                    k in err_str
                    for k in ["connection closed", "connection reset", "broken pipe", "timeout", "socket"]
                )
                if is_connection_err and attempt < max_retries:
                    logger.warning(
                        f"Transient FalkorDB query error (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying..."
                    )
                    with self._conn_lock:
                        self._connected = False
                        self._db = None
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise e
        raise last_error


db_client = FalkorDBClient.get_instance()
