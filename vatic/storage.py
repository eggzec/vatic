# -------------------------------------*- vatic -*----------------------------
#                               Open Source Risk Analysis
#
#                             Copyright (c) 2026, eggzec
#                          Contact: https://eggzec.github.io/
#
#                         License: GNU General Public License
#                              Version 3, 29 June 2007
#
# ----------------------------------------------------------------------------
#
#  Author(s)
#      Saud Zahir <m.saud.zahir@gmail.com>
#
#  Date
#      7 May 2026
#
#  Description
#      SQLite persistence for saved analyses.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class AnalysisSummary:
    analysis_id: int
    name: str
    updated_at: str


@dataclass(frozen=True)
class AnalysisRecord:
    analysis_id: int
    name: str
    formula: str
    iterations: int
    assumptions: list[dict[str, object]]
    updated_at: str


class AnalysisStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("Initializing analysis store | db_path=%s", self.db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        LOGGER.debug("Opening sqlite connection | db_path=%s", self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    formula TEXT NOT NULL,
                    iterations INTEGER NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        LOGGER.debug("Database schema ensured")

    def save_analysis(
        self,
        name: str,
        formula: str,
        iterations: int,
        assumptions: list[dict[str, object]],
    ) -> int:
        assumptions_json = json.dumps(
            assumptions, separators=(",", ":"), sort_keys=True
        )
        LOGGER.debug(
            "Saving analysis | name=%s | iterations=%s | assumptions=%s",
            name,
            iterations,
            len(assumptions),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analyses (name, formula, iterations, assumptions_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    formula = excluded.formula,
                    iterations = excluded.iterations,
                    assumptions_json = excluded.assumptions_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, formula, iterations, assumptions_json),
            )
            row = conn.execute(
                "SELECT id FROM analyses WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to save analysis")
            saved_id = int(row["id"])
            LOGGER.debug("Analysis saved | id=%s | name=%s", saved_id, name)
            return saved_id

    def list_analyses(self) -> list[AnalysisSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, updated_at
                FROM analyses
                ORDER BY updated_at DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        LOGGER.debug("Loaded analysis list | count=%s", len(rows))
        return [
            AnalysisSummary(
                analysis_id=int(row["id"]),
                name=str(row["name"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def get_analysis(self, analysis_id: int) -> AnalysisRecord | None:
        LOGGER.debug("Loading analysis | id=%s", analysis_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, formula, iterations, assumptions_json, updated_at
                FROM analyses
                WHERE id = ?
                """,
                (analysis_id,),
            ).fetchone()
        if row is None:
            LOGGER.warning("Analysis not found | id=%s", analysis_id)
            return None
        assumptions = json.loads(str(row["assumptions_json"]))
        LOGGER.debug(
            "Analysis loaded | id=%s | name=%s | assumptions=%s",
            analysis_id,
            str(row["name"]),
            len(assumptions),
        )
        return AnalysisRecord(
            analysis_id=int(row["id"]),
            name=str(row["name"]),
            formula=str(row["formula"]),
            iterations=int(row["iterations"]),
            assumptions=assumptions,
            updated_at=str(row["updated_at"]),
        )
