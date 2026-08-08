import pandas as pd
import portfolio_crypto_data.nexo_dashboard as nexo_data
from portfolio_core import active_context


def _transactions_folder():
    folder = active_context().paths.crypto_transactions / "cex" / "nexo"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def test_missing_nexo_snapshot_file_returns_empty_dashboard_data() -> None:

    result = nexo_data.load_and_process_nexo_data(end_date_str="2026-01-04")

    assert result.empty
    assert nexo_data.list_nexo_coins() == []


def test_recent_nexo_transactions_excludes_internal_and_term_rows() -> None:
    tx_path = _transactions_folder() / "nexo.csv"
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

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-04",
        coins=None,
        limit=5,
    )

    assert list(result["Type"]) == ["Interest", "Exchange"]
    assert list(result["Date"]) == ["2026-01-03 10:00", "2026-01-02 10:00"]


def test_recent_nexo_transactions_coin_filter_applies_after_exclusions() -> None:
    tx_path = _transactions_folder() / "nexo.csv"
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

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-05",
        coins=["BTC"],
        limit=5,
    )

    assert list(result["Type"]) == ["Exchange"]


def test_recent_nexo_transactions_canonicalizes_usd_debt_bucket() -> None:
    pd.DataFrame(
        [
            {
                "Type": "Nexo Card Purchase",
                "Input Currency": "xUSD",
                "Input Amount": "-10.06",
                "Output Currency": "EUR",
                "Output Amount": "8.75",
                "Details": "approved / card merchant",
                "Date / Time (UTC)": "03/01/2026 10:00",
            },
            {
                "Type": "Nexo Card Refund",
                "Input Currency": "USDX",
                "Input Amount": "10.06",
                "Output Currency": "EUR",
                "Output Amount": "8.75",
                "Details": "approved / card merchant",
                "Date / Time (UTC)": "02/01/2026 10:00",
            },
            {
                "Type": "Exchange",
                "Input Currency": "USDT",
                "Input Amount": "-2",
                "Output Currency": "BTC",
                "Output Amount": "0.00005",
                "Details": "approved / exchange",
                "Date / Time (UTC)": "01/01/2026 10:00",
            },
        ]
    ).to_csv(_transactions_folder() / "nexo.csv", index=False)

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-04",
        coins=["USD"],
        limit=None,
    )

    assert list(result["Type"]) == ["Nexo Card Purchase", "Nexo Card Refund"]


def test_recent_nexo_transactions_reads_all_csv_files_in_folder() -> None:
    transactions_folder = _transactions_folder()
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
    ).to_csv(transactions_folder / "nexo_part_1.csv", index=False)
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
    ).to_csv(transactions_folder / "nexo_part_2.csv", index=False)

    result = nexo_data.load_recent_nexo_transactions(
        end_date_str="2026-01-04",
        coins=None,
        limit=5,
    )

    assert list(result["Type"]) == ["Interest", "Exchange"]
