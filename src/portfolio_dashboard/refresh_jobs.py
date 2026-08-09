from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

RefreshKind = Literal["prices", "transactions", "crypto", "all"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class RefreshAlreadyRunningError(RuntimeError):
    """Raised when a second mutating refresh is requested."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class RefreshJob:
    id: str
    kind: RefreshKind
    status: JobStatus = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    current_step: str | None = None
    error: str | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=400))

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "currentStep": self.current_step,
            "error": self.error,
            "logs": list(self.logs),
        }


class RefreshJobManager:
    """Run one data refresh at a time and retain a bounded in-memory history."""

    def __init__(self, *, history_limit: int = 20):
        self._jobs: dict[str, RefreshJob] = {}
        self._job_order: deque[str] = deque(maxlen=history_limit)
        self._lock = threading.Lock()

    def start(self, *, kind: RefreshKind, data_dir: Path) -> dict[str, object]:
        with self._lock:
            if any(job.status in {"queued", "running"} for job in self._jobs.values()):
                raise RefreshAlreadyRunningError("A data refresh is already running")
            if len(self._job_order) == self._job_order.maxlen:
                expired_id = self._job_order[0]
                self._jobs.pop(expired_id, None)
            job = RefreshJob(id=uuid4().hex, kind=kind)
            self._jobs[job.id] = job
            self._job_order.append(job.id)

        threading.Thread(
            target=self._run,
            kwargs={"job_id": job.id, "data_dir": data_dir},
            daemon=True,
            name=f"portfolio-refresh-{job.id[:8]}",
        ).start()
        return job.as_dict()

    def get(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def _steps(self, kind: RefreshKind, data_dir: Path) -> list[tuple[str, list[str]]]:
        prefix = [sys.executable, "-m"]
        market = [*prefix, "portfolio_market_data.cli", "--data-dir", str(data_dir)]
        crypto = [*prefix, "portfolio_crypto_data.cli", "--data-dir", str(data_dir)]
        steps = {
            "prices": [("Market prices", [*market, "prices", "update"])],
            "transactions": [("Getquin transactions", [*market, "transactions", "update"])],
            "crypto": [("Crypto data", [*crypto, "update"])],
        }
        if kind == "all":
            return [*steps["prices"], *steps["transactions"], *steps["crypto"]]
        return steps[kind]

    def _execute(self, *, command: list[str], data_dir: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PORTFOLIO_DATA_DIR"] = str(data_dir)
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def _run(self, *, job_id: str, data_dir: Path) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = _now()

        try:
            for label, command in self._steps(job.kind, data_dir):
                with self._lock:
                    job.current_step = label
                    job.logs.append(f"Starting {label}")
                result = self._execute(command=command, data_dir=data_dir)
                output = "\n".join(
                    part.strip() for part in (result.stdout, result.stderr) if part.strip()
                )
                with self._lock:
                    if output:
                        job.logs.extend(output.splitlines())
                if result.returncode:
                    raise RuntimeError(f"{label} failed with exit code {result.returncode}")
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.logs.append(str(exc))
        else:
            with self._lock:
                job.status = "succeeded"
                job.logs.append("Refresh completed")
        finally:
            with self._lock:
                job.current_step = None
                job.finished_at = _now()


refresh_jobs = RefreshJobManager()
