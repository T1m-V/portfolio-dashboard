from collections.abc import Iterator
from pathlib import Path

import pytest
from portfolio_core import PortfolioContext


@pytest.fixture(autouse=True)
def portfolio_context(tmp_path: Path) -> Iterator[PortfolioContext]:
    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    for folder in (
        context.paths.config,
        context.paths.real_estate,
        context.paths.dashboard_artifacts,
        context.paths.prices,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    with context.activate():
        yield context
