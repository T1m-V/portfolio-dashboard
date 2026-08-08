from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from portfolio_core import active_context

import portfolio_dashboard.main as main
from portfolio_dashboard.refresh_jobs import RefreshAlreadyRunningError, RefreshJobManager


def test_refresh_manager_runs_all_steps_in_order(tmp_path: Path, monkeypatch) -> None:
    manager = RefreshJobManager()
    started = threading.Event()
    release = threading.Event()
    commands: list[list[str]] = []

    def execute(*, command: list[str], data_dir: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        started.set()
        release.wait(timeout=2)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(manager, "_execute", execute)
    job = manager.start(kind="all", data_dir=tmp_path)
    assert started.wait(timeout=2)
    with pytest.raises(RefreshAlreadyRunningError):
        manager.start(kind="prices", data_dir=tmp_path)

    release.set()
    for _ in range(100):
        result = manager.get(str(job["id"]))
        if result and result["status"] == "succeeded":
            break
        threading.Event().wait(0.01)

    assert result is not None
    assert result["status"] == "succeeded"
    assert [command[2] for command in commands] == [
        "portfolio_market_data.cli",
        "portfolio_market_data.cli",
        "portfolio_crypto_data.cli",
    ]


def test_refresh_api_returns_job_and_handles_missing_job(monkeypatch) -> None:
    expected = {
        "id": "job-1",
        "kind": "prices",
        "status": "queued",
        "logs": [],
    }

    class FakeJobs:
        def start(self, **_kwargs):
            return expected

        def list(self):
            return [expected]

        def get(self, job_id: str):
            return expected if job_id == "job-1" else None

    client = TestClient(main.create_app(context=active_context(), jobs=FakeJobs()))

    assert client.post("/api/refresh/prices").status_code == 202
    assert client.get("/api/refresh/jobs").json() == [expected]
    assert client.get("/api/refresh/jobs/job-1").json() == expected
    assert client.get("/api/refresh/jobs/missing").status_code == 404
