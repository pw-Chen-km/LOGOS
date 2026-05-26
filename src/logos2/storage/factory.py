"""Graph repository factory."""

from __future__ import annotations

import os
from typing import Any

from ..config import LogosConfig
from .graph_repository import GraphRepositoryProtocol
from .sqlite_graph_repository import SQLiteGraphRepository


def create_graph_repository(
    config: LogosConfig,
    *,
    neo4j_uri: str | None = None,
    neo4j_user: str | None = None,
    neo4j_password: str | None = None,
) -> GraphRepositoryProtocol:
    """Create graph repository from LOGOS config."""
    backend = config.graph.backend.lower()
    if backend == "sqlite":
        return SQLiteGraphRepository(config.graph.sqlite_path)
    if backend == "neo4j":
        try:
            from .neo4j_repository import Neo4jRepository
        except Exception as exc:
            raise RuntimeError(
                "Neo4j backend requested but neo4j dependencies are unavailable. "
                "Use graph.backend=sqlite or fix the Neo4j Python environment."
            ) from exc
        return Neo4jRepository(
            uri=neo4j_uri or os.getenv(config.neo4j.uri_env),
            user=neo4j_user or os.getenv(config.neo4j.user_env),
            password=neo4j_password or os.getenv(config.neo4j.password_env),
        )
    raise ValueError(f"Unsupported graph backend: {config.graph.backend}")


def graph_repository_counts(repository: Any) -> tuple[int | None, int | None]:
    """Return paper/relation counts when supported by the backend."""
    if hasattr(repository, "count_papers") and hasattr(repository, "count_relations"):
        repository.connect()
        repository.setup_schema()
        return repository.count_papers(), repository.count_relations()
    return None, None
