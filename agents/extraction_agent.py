"""
EXTRACTION AGENT
Reads source tables in configurable batches using SQLAlchemy.
Password is URL-encoded to handle special characters such as @ in the password string.
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

load_dotenv()


def _source_engine():
    host = os.getenv("SOURCE_DB_HOST", "localhost")
    port = os.getenv("SOURCE_DB_PORT", "5432")
    dbname = os.getenv("SOURCE_DB_NAME", "legacy_bank_db")
    user = os.getenv("SOURCE_DB_USER", "postgres")
    password = quote_plus(os.getenv("SOURCE_DB_PASS", ""))
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}",
        pool_pre_ping=True,
    )


def extract_all_data(schema_mapping=None, progress_callback=None) -> dict:
    print("\n========== EXTRACTION AGENT ==========")

    if schema_mapping is None:
        from config.schema_mapping import get_default_mapping
        schema_mapping = get_default_mapping()

    batch_size = schema_mapping.get("batch_size", 50_000)
    engine = _source_engine()
    extracted = {}

    with engine.connect() as conn:
        for table_name, table_config in schema_mapping["tables"].items():
            source_table = table_config["source_table"]

            total_count = conn.execute(
                text(f"SELECT COUNT(*) FROM {source_table}")
            ).scalar()

            if total_count == 0:
                extracted[table_name] = pd.DataFrame()
                print(f"  {source_table}: 0 records (empty table)")
                continue

            batches = []
            offset = 0

            while offset < total_count:
                df = pd.read_sql(
                    text(
                        f"SELECT * FROM {source_table} LIMIT :limit OFFSET :offset"
                    ),
                    conn,
                    params={"limit": batch_size, "offset": offset},
                )
                if not df.empty:
                    batches.append(df)
                    current = offset + len(df)
                    if progress_callback:
                        progress_callback(
                            "extraction", table_name, current, total_count)
                offset += batch_size

            extracted[table_name] = (
                pd.concat(
                    batches, ignore_index=True) if batches else pd.DataFrame()
            )
            print(
                f"  Extracted {len(extracted[table_name]):,} records from {source_table}")

    engine.dispose()
    return extracted
