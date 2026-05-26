"""SQLite-backed lightweight research graph.

This is the default LOGOS graph backend.  It stores routing metadata only and
requires no graph server.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..schemas import (
    BaselineMatrixEntry,
    BenchmarkMatrixEntry,
    CandidateEdge,
    CandidateRelation,
    DatasetMatrixEntry,
    MethodFamily,
    PaperProfile,
    SurveyTaxonomy,
    Theme,
    VerifiedEdge,
)


class SQLiteGraphRepository:
    """SQLite implementation of LOGOS's lightweight graph repository."""

    def __init__(self, db_path: str | Path = "graph_index.sqlite"):
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> "SQLiteGraphRepository":
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def setup_schema(self) -> None:
        conn = self._connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                year TEXT,
                venue TEXT,
                tldr TEXT,
                theme TEXT,
                taxonomy_path_json TEXT,
                method_family TEXT,
                rough_problem TEXT,
                rough_contribution TEXT,
                reading_level TEXT,
                confidence REAL,
                skill_path TEXT,
                profile_path TEXT,
                pdf_path TEXT
            );

            CREATE TABLE IF NOT EXISTS themes (
                theme_id TEXT,
                name TEXT PRIMARY KEY,
                description TEXT,
                keywords_json TEXT
            );

            CREATE TABLE IF NOT EXISTS method_families (
                family_id TEXT,
                name TEXT PRIMARY KEY,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS benchmarks (
                name TEXT PRIMARY KEY,
                metric_names_json TEXT
            );

            CREATE TABLE IF NOT EXISTS datasets (
                name TEXT PRIMARY KEY,
                task_types_json TEXT
            );

            CREATE TABLE IF NOT EXISTS baselines (
                name TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS paper_theme (
                paper_id TEXT,
                theme_name TEXT,
                PRIMARY KEY (paper_id, theme_name)
            );

            CREATE TABLE IF NOT EXISTS paper_method_family (
                paper_id TEXT,
                method_family_name TEXT,
                PRIMARY KEY (paper_id, method_family_name)
            );

            CREATE TABLE IF NOT EXISTS paper_benchmark (
                paper_id TEXT,
                benchmark_name TEXT,
                PRIMARY KEY (paper_id, benchmark_name)
            );

            CREATE TABLE IF NOT EXISTS paper_dataset (
                paper_id TEXT,
                dataset_name TEXT,
                PRIMARY KEY (paper_id, dataset_name)
            );

            CREATE TABLE IF NOT EXISTS paper_baseline (
                paper_id TEXT,
                baseline_name TEXT,
                PRIMARY KEY (paper_id, baseline_name)
            );

            CREATE TABLE IF NOT EXISTS paper_edges (
                source_paper_id TEXT,
                target_paper_id TEXT,
                relation_type TEXT,
                status TEXT,
                source TEXT,
                confidence REAL,
                rationale TEXT,
                verified INTEGER DEFAULT 0,
                verified_at TEXT,
                verifier_version TEXT,
                PRIMARY KEY (source_paper_id, target_paper_id, relation_type)
            );

            CREATE INDEX IF NOT EXISTS idx_papers_theme ON papers(theme);
            CREATE INDEX IF NOT EXISTS idx_papers_method ON papers(method_family);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON paper_edges(source_paper_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON paper_edges(target_paper_id);
            """
        )
        conn.commit()

    def create_paper_node(self, profile: PaperProfile) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO papers (
                paper_id, title, year, venue, tldr, theme, taxonomy_path_json,
                method_family, rough_problem, rough_contribution, reading_level,
                confidence, skill_path, profile_path, pdf_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                title=excluded.title,
                year=excluded.year,
                venue=excluded.venue,
                tldr=excluded.tldr,
                theme=excluded.theme,
                taxonomy_path_json=excluded.taxonomy_path_json,
                method_family=excluded.method_family,
                rough_problem=excluded.rough_problem,
                rough_contribution=excluded.rough_contribution,
                reading_level=excluded.reading_level,
                confidence=excluded.confidence,
                skill_path=excluded.skill_path,
                profile_path=excluded.profile_path,
                pdf_path=excluded.pdf_path
            """,
            (
                profile.paper_id,
                profile.title,
                profile.year,
                profile.venue,
                profile.tldr,
                profile.theme,
                json.dumps(profile.taxonomy_path, ensure_ascii=False),
                profile.method_family,
                profile.rough_research_problem,
                profile.rough_contribution,
                profile.reading_level,
                profile.confidence,
                profile.skill_path,
                profile.skill_path.replace("SKILL.md", "paper_profile.json")
                if profile.skill_path
                else "",
                profile.pdf_path,
            ),
        )
        conn.commit()

    def create_theme_nodes(self, themes: list[Theme]) -> None:
        conn = self._connection()
        conn.executemany(
            """
            INSERT INTO themes (theme_id, name, description, keywords_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                theme_id=excluded.theme_id,
                description=excluded.description,
                keywords_json=excluded.keywords_json
            """,
            [
                (
                    theme.theme_id,
                    theme.name,
                    theme.description,
                    json.dumps(theme.keywords, ensure_ascii=False),
                )
                for theme in themes
            ],
        )
        conn.commit()

    def create_method_family_nodes(self, families: list[MethodFamily]) -> None:
        conn = self._connection()
        conn.executemany(
            """
            INSERT INTO method_families (family_id, name, description)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                family_id=excluded.family_id,
                description=excluded.description
            """,
            [(family.family_id, family.name, family.description) for family in families],
        )
        conn.commit()

    def create_benchmark_nodes(self, benchmarks: list[BenchmarkMatrixEntry]) -> None:
        conn = self._connection()
        conn.executemany(
            """
            INSERT INTO benchmarks (name, metric_names_json)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET metric_names_json=excluded.metric_names_json
            """,
            [
                (
                    benchmark.benchmark_name,
                    json.dumps(benchmark.metric_names, ensure_ascii=False),
                )
                for benchmark in benchmarks
            ],
        )
        conn.commit()

    def create_dataset_nodes(self, datasets: list[DatasetMatrixEntry]) -> None:
        conn = self._connection()
        conn.executemany(
            """
            INSERT INTO datasets (name, task_types_json)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET task_types_json=excluded.task_types_json
            """,
            [
                (
                    dataset.dataset_name,
                    json.dumps(dataset.task_types, ensure_ascii=False),
                )
                for dataset in datasets
            ],
        )
        conn.commit()

    def create_baseline_nodes(self, baselines: list[BaselineMatrixEntry]) -> None:
        conn = self._connection()
        conn.executemany(
            "INSERT OR IGNORE INTO baselines (name) VALUES (?)",
            [(baseline.baseline_name,) for baseline in baselines],
        )
        conn.commit()

    def create_paper_relationships(
        self,
        profile: PaperProfile,
        taxonomy: SurveyTaxonomy,
    ) -> None:
        conn = self._connection()
        if profile.theme:
            conn.execute(
                "INSERT OR IGNORE INTO paper_theme (paper_id, theme_name) VALUES (?, ?)",
                (profile.paper_id, profile.theme),
            )
        if profile.method_family:
            conn.execute(
                """
                INSERT OR IGNORE INTO paper_method_family
                (paper_id, method_family_name) VALUES (?, ?)
                """,
                (profile.paper_id, profile.method_family),
            )
        conn.executemany(
            "INSERT OR IGNORE INTO paper_benchmark (paper_id, benchmark_name) VALUES (?, ?)",
            [(profile.paper_id, name) for name in profile.benchmark_names],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO paper_dataset (paper_id, dataset_name) VALUES (?, ?)",
            [(profile.paper_id, name) for name in profile.dataset_names],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO paper_baseline (paper_id, baseline_name) VALUES (?, ?)",
            [(profile.paper_id, name) for name in profile.baseline_names],
        )
        conn.commit()

    def create_candidate_relation(self, edge: CandidateEdge) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO paper_edges (
                source_paper_id, target_paper_id, relation_type, status, source,
                confidence, rationale, verified
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(source_paper_id, target_paper_id, relation_type) DO UPDATE SET
                status=excluded.status,
                source=excluded.source,
                confidence=excluded.confidence,
                rationale=excluded.rationale
            """,
            (
                edge.source_paper_id,
                edge.target_paper_id,
                edge.relation_type,
                edge.status,
                edge.source,
                edge.confidence,
                edge.rationale,
            ),
        )
        conn.commit()

    def update_relation_status(self, edge: VerifiedEdge) -> None:
        conn = self._connection()
        conn.execute(
            """
            UPDATE paper_edges
            SET status = ?, confidence = ?, verified = 1,
                verified_at = ?, verifier_version = ?
            WHERE source_paper_id = ?
              AND target_paper_id = ?
              AND relation_type = ?
            """,
            (
                edge.status,
                edge.confidence,
                edge.verified_at,
                edge.verifier_version,
                edge.source_paper_id,
                edge.target_paper_id,
                edge.relation_type,
            ),
        )
        conn.commit()

    def search_papers_by_theme(self, theme_name: str) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            """
            SELECT paper_id, title, tldr, skill_path, confidence
            FROM papers
            WHERE lower(theme) = lower(?)
               OR paper_id IN (
                   SELECT paper_id FROM paper_theme WHERE lower(theme_name) = lower(?)
               )
            """,
            (theme_name, theme_name),
        )
        return [_row_to_dict(row) for row in rows.fetchall()]

    def search_papers_by_benchmark(self, benchmark_name: str) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            """
            SELECT p.paper_id, p.title, p.tldr, p.skill_path
            FROM papers p
            JOIN paper_benchmark b ON p.paper_id = b.paper_id
            WHERE lower(b.benchmark_name) = lower(?)
            """,
            (benchmark_name,),
        )
        return [_row_to_dict(row) for row in rows.fetchall()]

    def get_paper_neighbors(
        self,
        paper_id: str,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            """
            SELECT p.paper_id, p.title, e.relation_type, e.confidence, e.status, p.skill_path
            FROM paper_edges e
            JOIN papers p ON p.paper_id = e.target_paper_id
            WHERE e.source_paper_id = ?
              AND e.confidence >= ?
            ORDER BY e.confidence DESC
            """,
            (paper_id, min_confidence),
        )
        return [_row_to_dict(row) for row in rows.fetchall()]

    def fulltext_search_papers(
        self,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        terms = [term.lower() for term in query_text.split() if len(term) >= 3]
        if not terms:
            terms = [query_text.lower()]
        clauses = []
        params: list[Any] = []
        for term in terms[:8]:
            like = f"%{term}%"
            clauses.append(
                """
                lower(title) LIKE ?
                OR lower(tldr) LIKE ?
                OR lower(theme) LIKE ?
                OR lower(method_family) LIKE ?
                """
            )
            params.extend([like, like, like, like])

        query = f"""
            SELECT paper_id, title, tldr, skill_path, confidence
            FROM papers
            WHERE {" OR ".join(f"({clause})" for clause in clauses)}
            ORDER BY confidence DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self._connection().execute(query, params)
        return [_row_to_dict(row) for row in rows.fetchall()]

    def count_papers(self) -> int:
        row = self._connection().execute("SELECT COUNT(*) AS count FROM papers").fetchone()
        return int(row["count"])

    def count_relations(self) -> int:
        row = self._connection().execute("SELECT COUNT(*) AS count FROM paper_edges").fetchone()
        return int(row["count"])

    def _connection(self) -> sqlite3.Connection:
        if self.conn is None:
            self.connect()
        assert self.conn is not None
        return self.conn


class LightweightSQLiteIndexer:
    """Compatibility indexer wrapper for SQLiteGraphRepository."""

    def __init__(self, repository: SQLiteGraphRepository | None = None):
        self.repository = repository or SQLiteGraphRepository()

    def index_taxonomy(self, taxonomy: SurveyTaxonomy) -> None:
        self.repository.connect()
        self.repository.setup_schema()
        self.repository.create_theme_nodes(taxonomy.themes)
        self.repository.create_method_family_nodes(taxonomy.method_families)
        self.repository.create_benchmark_nodes(taxonomy.benchmark_matrix)
        self.repository.create_dataset_nodes(taxonomy.dataset_matrix)
        self.repository.create_baseline_nodes(taxonomy.baseline_matrix)

    def index_paper(self, profile: PaperProfile, taxonomy: SurveyTaxonomy) -> None:
        self.repository.create_paper_node(profile)
        self.repository.create_paper_relationships(profile, taxonomy)

    def index_papers_batch(
        self,
        profiles: list[PaperProfile],
        taxonomy: SurveyTaxonomy,
    ) -> None:
        for profile in profiles:
            self.index_paper(profile, taxonomy)

    def index_candidate_relations(self, relations: list[CandidateRelation]) -> None:
        for relation in relations:
            edge = CandidateEdge(
                source_paper_id=relation.source_paper_id,
                target_paper_id=relation.target_paper_id,
                relation_type=relation.relation_type,
                status=relation.status,
                source=relation.source,
                confidence=relation.confidence,
                rationale=relation.rationale,
            )
            self.repository.create_candidate_relation(edge)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
