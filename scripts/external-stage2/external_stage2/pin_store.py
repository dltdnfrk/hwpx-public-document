from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class PinRecord:
    receipt_digest: str
    semantic_pass: bool
    reason_codes: Tuple[str, ...]
    issued_at: str
    retry_of_execution_id: Optional[str]


@dataclass(frozen=True)
class PinOutcome:
    status: str
    record: Optional[PinRecord]


class PinStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pins (
                    project_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    semantic_pass INTEGER NOT NULL CHECK (semantic_pass IN (0, 1)),
                    reason_codes_json TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    retry_of_execution_id TEXT,
                    PRIMARY KEY (project_id, execution_id)
                );
                CREATE TABLE IF NOT EXISTS equivocations (
                    project_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    pinned_receipt_digest TEXT NOT NULL,
                    conflicting_receipt_digest TEXT NOT NULL,
                    PRIMARY KEY (
                        project_id,
                        execution_id,
                        conflicting_receipt_digest
                    )
                );
                """
            )

    def get(self, project_id: str, execution_id: str) -> Optional[PinRecord]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT receipt_digest, semantic_pass, reason_codes_json,
                       issued_at, retry_of_execution_id
                FROM pins
                WHERE project_id = ? AND execution_id = ?
                """,
                (project_id, execution_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def pin_first(
        self,
        project_id: str,
        execution_id: str,
        receipt_digest: str,
        semantic_pass: bool,
        reason_codes: Tuple[str, ...],
        issued_at: str,
        retry_of_execution_id: Optional[str],
    ) -> PinOutcome:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT receipt_digest, semantic_pass, reason_codes_json,
                       issued_at, retry_of_execution_id
                FROM pins
                WHERE project_id = ? AND execution_id = ?
                """,
                (project_id, execution_id),
            ).fetchone()
            if row is not None:
                record = self._record(row)
                if record.receipt_digest == receipt_digest:
                    connection.commit()
                    return PinOutcome("IDEMPOTENT", record)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO equivocations (
                        project_id, execution_id, pinned_receipt_digest,
                        conflicting_receipt_digest
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (project_id, execution_id, record.receipt_digest, receipt_digest),
                )
                connection.commit()
                return PinOutcome("EQUIVOCATION", record)
            if retry_of_execution_id is not None:
                prior = connection.execute(
                    """
                    SELECT 1 FROM pins
                    WHERE project_id = ? AND execution_id = ?
                    """,
                    (project_id, retry_of_execution_id),
                ).fetchone()
                if prior is None:
                    connection.rollback()
                    return PinOutcome("RETRY_LINK_INVALID", None)
            connection.execute(
                """
                INSERT INTO pins (
                    project_id, execution_id, receipt_digest, semantic_pass,
                    reason_codes_json, issued_at, retry_of_execution_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    execution_id,
                    receipt_digest,
                    int(semantic_pass),
                    json.dumps(reason_codes, separators=(",", ":")),
                    issued_at,
                    retry_of_execution_id,
                ),
            )
            connection.commit()
            return PinOutcome("PINNED", None)
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30)

    @staticmethod
    def _record(row: Tuple[str, int, str, str, Optional[str]]) -> PinRecord:
        decoded = json.loads(row[2])
        if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
            raise sqlite3.DatabaseError("invalid pinned reason codes")
        return PinRecord(
            receipt_digest=row[0],
            semantic_pass=bool(row[1]),
            reason_codes=tuple(decoded),
            issued_at=row[3],
            retry_of_execution_id=row[4],
        )
