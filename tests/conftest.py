from collections.abc import Iterator
from pathlib import Path

import pytest
from portfolio_core import PortfolioContext


@pytest.fixture(autouse=True)
def portfolio_context(tmp_path: Path) -> Iterator[PortfolioContext]:
    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    context.paths.config.mkdir(parents=True, exist_ok=True)
    context.paths.real_estate.mkdir(parents=True, exist_ok=True)
    context.paths.crypto_snapshots.mkdir(parents=True, exist_ok=True)
    context.paths.crypto_transactions.mkdir(parents=True, exist_ok=True)
    context.paths.dashboard_artifacts.mkdir(parents=True, exist_ok=True)
    context.paths.prices.mkdir(parents=True, exist_ok=True)
    with context.activate():
        yield context
