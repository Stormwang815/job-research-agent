import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class TaskRepository:
    def __init__(self, path: Path, recover_interrupted: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._initialize(recover_interrupted)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self, recover_interrupted: bool) -> None:
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    city TEXT NOT NULL,
                    seniority TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
                    current_stage TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                    report TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    source_count INTEGER NOT NULL DEFAULT 0,
                    elapsed_seconds REAL NOT NULL DEFAULT 0,
                    estimated_cost REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES research_tasks(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT '',
                    trust_tier TEXT NOT NULL,
                    trust_score INTEGER NOT NULL,
                    UNIQUE(task_id, url)
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON research_tasks(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON research_tasks(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sources_task_id ON research_sources(task_id);
                """
            )
            if recover_interrupted:
                db.execute("UPDATE research_tasks SET status='failed', current_stage='error', progress=100, error='服务重启导致任务中断，请重新运行', updated_at=? WHERE status IN ('queued','running')", (self._now(),))
            db.execute("PRAGMA optimize")

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def create(self, task_id: str, request: dict[str, Any]) -> None:
        now = self._now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO research_tasks(id,role,city,seniority,request_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'queued',?,?)",
                (task_id, request["role"], request["city"], request["seniority"], json.dumps(request, ensure_ascii=False), now, now),
            )

    def update(self, task_id: str, **fields: Any) -> None:
        allowed = {"status", "current_stage", "progress", "report", "error", "source_count", "elapsed_seconds", "estimated_cost"}
        clean = {key: value for key, value in fields.items() if key in allowed}
        if not clean:
            return
        clean["updated_at"] = self._now()
        assignments = ",".join(f"{key}=?" for key in clean)
        with self._lock, self._connect() as db:
            db.execute(f"UPDATE research_tasks SET {assignments} WHERE id=?", (*clean.values(), task_id))

    def add_sources(self, task_id: str, sources: list[dict[str, Any]]) -> None:
        rows = [(task_id, s["url"], s["title"], s["domain"], s["trust_tier"], s["trust_score"]) for s in sources]
        with self._lock, self._connect() as db:
            db.executemany(
                "INSERT OR IGNORE INTO research_sources(task_id,url,title,domain,trust_tier,trust_score) VALUES(?,?,?,?,?,?)",
                rows,
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["request"] = json.loads(result.pop("request_json"))
            result["sources"] = [dict(item) for item in db.execute("SELECT url,title,domain,trust_tier,trust_score FROM research_sources WHERE task_id=? ORDER BY trust_score DESC", (task_id,))]
            return result

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,role,city,seniority,status,current_stage,progress,source_count,elapsed_seconds,estimated_cost,created_at,updated_at,error FROM research_tasks ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [dict(row) for row in rows]
