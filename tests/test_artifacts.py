import pandas as pd
import pytest
from portfolio_core import active_context

from portfolio_dashboard.arbitrum import (
    ARTIFACT_FILES,
    load_arbitrum_artifacts,
)


def test_arbitrum_reader_uses_only_the_consumed_strict_contract() -> None:
    root = active_context().paths.dashboard_artifacts / "arbitrum"
    root.mkdir()
    for filename, columns in ARTIFACT_FILES.values():
        pd.DataFrame(columns=columns).to_csv(root / filename, index=False)
    (root / "asset_daily.csv").write_text("unused,malformed\n")

    artifacts = load_arbitrum_artifacts()
    assert artifacts.warnings == []
    assert not hasattr(artifacts, "asset_daily")

    pd.DataFrame(columns=["old", "schema"]).to_csv(root / "timeseries_daily.csv", index=False)
    with pytest.raises(ValueError, match="Invalid Arbitrum artifact schema"):
        load_arbitrum_artifacts()


def test_missing_arbitrum_artifacts_return_canonical_empty_frames() -> None:
    artifacts = load_arbitrum_artifacts()
    assert len(artifacts.warnings) == len(ARTIFACT_FILES)
    assert list(artifacts.timeseries.columns) == ARTIFACT_FILES["timeseries"][1]
