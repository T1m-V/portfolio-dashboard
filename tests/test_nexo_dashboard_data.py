from pathlib import Path

import pandas as pd

import dashboard.data_handling.nexo_data as nexo_data


def test_recent_nexo_transactions_excludes_internal_and_term_rows(
    monkeypatch, tmp_path: Path
) -> None:
    tx_path = tmp_path / "nexo.csv"
    pd.DataFrame(
        [
            {
                "Type": "Interest",
                "Input Currency": "NEXO",
                "Input Amount": "1",
                "Output Currency": "NEXO",
                "Output Amount": "1",
                "Details": "approved / 0.5 BTC",
                "Date / Time (UTC)": "03/01/2026 10:00",
            },
            {
                "Type": "Locking Term Deposit",
                "Input Currency": "BTC",
                "Input Amount": "-0.1",
                "Output Currency": "BTC",
                "Output Amount": "0.1",
                "Details": "approved / Transfer from Savings Wallet to Term Wallet",
                "Date / Time (UTC)": "03/01/2026 09:00",
            },
            {
                "Type": "Transfer Out",
                "Input Currency": "USDC",
                "Input Amount": "-10",
                "Output Currency": "USDC",
                "Output Amount": "10",
                "Details": "approved / Transfer from Savings Wallet to Credit Line Wallet",
                "Date / Time (UTC)": "03/01/2026 08:00",
            },
            {
                "Type": "Exchange",
                "Input Currency": "USDT",
                "Input Amount": "-2",
                "Output Currency": "BTC",
                "Output Amount": "0.00005",
                "Details": "approved / exchange",
                "Date / Time (UTC)": "02/01/2026 10:00",
            },
        ]
    ).to_csv(tx_path, index=False)

    monkeypatch.setattr(nexo_data, "NEXO_TRANSACTIONS_FOLDER", tmp_path)

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-04",
        coins=None,
        limit=5,
    )

    assert list(result["Type"]) == ["Interest", "Exchange"]
    assert list(result["Date"]) == ["2026-01-03 10:00", "2026-01-02 10:00"]


def test_recent_nexo_transactions_coin_filter_applies_after_exclusions(
    monkeypatch, tmp_path: Path
) -> None:
    tx_path = tmp_path / "nexo.csv"
    pd.DataFrame(
        [
            {
                "Type": "Interest",
                "Input Currency": "NEXO",
                "Input Amount": "1",
                "Output Currency": "NEXO",
                "Output Amount": "1",
                "Details": "approved / 0.5 BTC",
                "Date / Time (UTC)": "03/01/2026 10:00",
            },
            {
                "Type": "Exchange",
                "Input Currency": "USDT",
                "Input Amount": "-2",
                "Output Currency": "BTC",
                "Output Amount": "0.00005",
                "Details": "approved / exchange",
                "Date / Time (UTC)": "02/01/2026 10:00",
            },
            {
                "Type": "Unlocking Term Deposit",
                "Input Currency": "BTC",
                "Input Amount": "0.2",
                "Output Currency": "BTC",
                "Output Amount": "0.2",
                "Details": "approved / Transfer from Term Wallet to Savings Wallet",
                "Date / Time (UTC)": "04/01/2026 10:00",
            },
        ]
    ).to_csv(tx_path, index=False)

    monkeypatch.setattr(nexo_data, "NEXO_TRANSACTIONS_FOLDER", tmp_path)

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-05",
        coins=["BTC"],
        limit=5,
    )

    assert list(result["Type"]) == ["Exchange"]


def test_recent_nexo_transactions_reads_all_csv_files_in_folder(
    monkeypatch, tmp_path: Path
) -> None:
    pd.DataFrame(
        [
            {
                "Type": "Interest",
                "Input Currency": "NEXO",
                "Input Amount": "1",
                "Output Currency": "NEXO",
                "Output Amount": "1",
                "Details": "approved / part one",
                "Date / Time (UTC)": "03/01/2026 10:00",
            }
        ]
    ).to_csv(tmp_path / "nexo_part_1.csv", index=False)
    pd.DataFrame(
        [
            {
                "Type": "Exchange",
                "Input Currency": "USDT",
                "Input Amount": "-2",
                "Output Currency": "BTC",
                "Output Amount": "0.00005",
                "Details": "approved / part two",
                "Date / Time (UTC)": "02/01/2026 10:00",
            }
        ]
    ).to_csv(tmp_path / "nexo_part_2.csv", index=False)

    monkeypatch.setattr(nexo_data, "NEXO_TRANSACTIONS_FOLDER", tmp_path)

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-04",
        coins=None,
        limit=5,
    )

    assert list(result["Type"]) == ["Interest", "Exchange"]
