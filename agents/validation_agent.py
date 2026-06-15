"""
VALIDATION AGENT
Hard-fails only on null identity/FK columns.
Negative balances, suspicious amounts, and similar data quality issues
are passed to the anomaly detection agent -- they do not block migration.
"""

import pandas as pd

# Only these columns can cause a hard validation failure.
# Every other quality concern (negative balances, status values, large amounts)
# is the remit of the anomaly detection agent.
CRITICAL_COLUMNS = {
    "branch":       ["BranchCode"],
    "customers":    ["CustomerId"],
    "accounts":     ["AccountId", "AccountNumber", "CustomerId"],
    "transactions": ["TransactionId", "AccountNumber"],
    "loans":        ["LoanId", "CustomerId"],
}

SAMPLE_PCT = 10  # sample percentage for large tables


def validate_data(transformed: dict) -> tuple[bool, dict]:
    print("\n========== VALIDATION AGENT ==========")
    issues = {}

    for table_name, df in transformed.items():
        if df is None or df.empty:
            continue

        total = len(df)
        table_issues = []

        if total > 100_000:
            sample_n = max(int(total * SAMPLE_PCT / 100), 1000)
            df_check = df.sample(n=min(sample_n, total), random_state=42)
            print(
                f"  Validating {table_name}: {total:,} records (sample {sample_n:,})")
        else:
            df_check = df
            print(f"  Validating {table_name}: {total:,} records (full)")

        for col in CRITICAL_COLUMNS.get(table_name, []):
            if col not in df_check.columns:
                continue
            nulls = int(df_check[col].isnull().sum())
            if nulls:
                estimated = int(nulls * total / len(df_check))
                table_issues.append(
                    f"{estimated:,} null values in '{col}' — identity column, cannot load"
                )

        if table_issues:
            issues[table_name] = table_issues

    passed = len(issues) == 0

    if passed:
        print("\nValidation PASSED")
    else:
        print(f"\nValidation FAILED")
        for table, errs in issues.items():
            for err in errs:
                print(f"  {table}: {err}")

    return passed, issues
