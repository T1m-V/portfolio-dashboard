import subprocess
import threading
from pathlib import Path

import pytest

from portfolio_dashboard.refresh_jobs import RefreshAlreadyRunningError, RefreshJobManager


def wait_for_job(manager: RefreshJobManager, job_id: str) -> dict:
    for _ in range(100):
        job = manager.get(job_id)
        if job and job["status"] not in {"queued", "running"}:
            return job
        threading.Event().wait(0.01)
    raise AssertionError("refresh job did not finish")


def test_refreshes_keep_the_loader_cli_boundary_and_run_one_at_a_time(
    tmp_path: Path, monkeypatch
) -> None:
    manager = RefreshJobManager()
    started = threading.Event()
    release = threading.Event()
    commands: list[list[str]] = []

    def execute(*, command: list[str], data_dir: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        started.set()
        release.wait(timeout=2)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(manager, "_execute", execute)
    job = manager.start(kind="all", data_dir=tmp_path)
    assert started.wait(timeout=2)
    with pytest.raises(RefreshAlreadyRunningError):
        manager.start(kind="prices", data_dir=tmp_path)
    release.set()

    assert wait_for_job(manager, str(job["id"]))["status"] == "succeeded"
    assert [(command[2], command[-2:]) for command in commands] == [
        ("portfolio_market_data.cli", ["prices", "update"]),
        ("portfolio_market_data.cli", ["transactions", "update"]),
        ("portfolio_crypto_data.cli", [str(tmp_path), "update"]),
    ]


def test_refresh_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    manager = RefreshJobManager()
    monkeypatch.setattr(
        manager,
        "_execute",
        lambda **_kwargs: subprocess.CompletedProcess([], 7, "", "bad input"),
    )
    job = manager.start(kind="prices", data_dir=tmp_path)
    result = wait_for_job(manager, str(job["id"]))
    assert result["status"] == "failed"
    assert result["error"] == "Market prices failed with exit code 7"
