"""
TRANSFORMATION AGENT
Applies column renaming and light data normalisation.
Does not modify source data; operates on in-memory DataFrames only.
"""

import pandas as pd


def transform_all_data(extracted: dict, schema_mapping=None, progress_callback=None) -> dict:
    print("\n========== TRANSFORMATION AGENT ==========")

    if schema_mapping is None:
        from config.schema_mapping import get_default_mapping
        schema_mapping = get_default_mapping()

    transformed = {}

    for idx, table_name in enumerate(extracted.keys()):
        df = extracted[table_name]

        if df is None or df.empty:
            transformed[table_name] = df
            continue

        col_mapping = schema_mapping["tables"][table_name]["columns"]

        # Rename only columns that exist in the DataFrame
        rename = {src: tgt for src, tgt in col_mapping.items()
                  if src in df.columns}
        df = df.rename(columns=rename)

        # Normalise customers
        if table_name == "customers":
            if "CustomerName" in df.columns:
                df["CustomerName"] = (
                    df["CustomerName"].astype(str).str.strip().str.title()
                )
            if "EmailAddress" in df.columns:
                df["EmailAddress"] = (
                    df["EmailAddress"].astype(str).str.strip().str.lower()
                )

        # Numeric coercion
        if table_name == "accounts" and "AccountBalance" in df.columns:
            df["AccountBalance"] = pd.to_numeric(
                df["AccountBalance"], errors="coerce"
            ).fillna(0.0)

        if table_name == "transactions" and "Amount" in df.columns:
            df["Amount"] = pd.to_numeric(
                df["Amount"], errors="coerce"
            ).fillna(0.0)

        if table_name == "loans" and "LoanAmount" in df.columns:
            df["LoanAmount"] = pd.to_numeric(
                df["LoanAmount"], errors="coerce"
            ).fillna(0.0)

        transformed[table_name] = df

        if progress_callback:
            progress_callback("transformation", table_name,
                              idx + 1, len(extracted))

        print(f"  Transformed {len(df):,} records for {table_name}")

    return transformed
