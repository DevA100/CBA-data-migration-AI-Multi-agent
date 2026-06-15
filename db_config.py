"""
DB CONFIG
Centralised database connection factory.
All credentials read from environment variables; .env loaded once here.
"""

import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv
import os

load_dotenv()


def _connect(host, port, dbname, user, password, label="database"):
    try:
        return psycopg2.connect(
            host=host,
            port=int(port),
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=10,
        )
    except OperationalError as exc:
        raise OperationalError(
            f"Cannot connect to {label} ({host}:{port}/{dbname}): {exc}"
        ) from exc


def get_source_connection():
    return _connect(
        host=os.getenv("SOURCE_DB_HOST", "localhost"),
        port=os.getenv("SOURCE_DB_PORT", "5432"),
        dbname=os.getenv("SOURCE_DB_NAME", "legacy_bank_db"),
        user=os.getenv("SOURCE_DB_USER", "postgres"),
        password=os.getenv("SOURCE_DB_PASS", ""),
        label="source (legacy_bank_db)",
    )


def get_target_connection():
    return _connect(
        host=os.getenv("TARGET_DB_HOST", "localhost"),
        port=os.getenv("TARGET_DB_PORT", "5432"),
        dbname=os.getenv("TARGET_DB_NAME", "target_bank_db"),
        user=os.getenv("TARGET_DB_USER", "postgres"),
        password=os.getenv("TARGET_DB_PASS", ""),
        label="target (target_bank_db)",
    )


get_legacy_connection = get_source_connection
