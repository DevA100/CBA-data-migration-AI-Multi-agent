"""
DATA MISMATCH LOGGER
Audit trail for all data quality issues detected during migration.
Thread-safe singleton.  All events written to a rotating JSONL file.
"""

import json
import os
import threading
from datetime import datetime, date
from typing import Any, Dict, List

import numpy as np


class DataMismatchLogger:
    """Records every data quality event during a migration run."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._lock = threading.Lock()
        self.mismatches: Dict[str, List[dict]] = {
            "orphaned_records":      [],
            "foreign_key_violations": [],
            "null_values":           [],
            "duplicate_keys":        [],
            "type_mismatches":       [],
            "schema_mismatches":     [],
            "batch_errors":          [],
            "backup_events":         [],
            "restore_events":        [],
            "verification_failures": [],
        }

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Cannot serialise type {type(obj)}")

    # ------------------------------------------------------------------
    # Internal write
    # ------------------------------------------------------------------

    def _record(self, category: str, entry: dict):
        with self._lock:
            self.mismatches[category].append(entry)
            date_str = datetime.now().strftime("%Y%m%d")
            path = os.path.join(
                self.log_dir, f"data_mismatches_{date_str}.jsonl")
            with open(path, "a") as fh:
                fh.write(json.dumps(entry, default=self._serialise) + "\n")

    # ------------------------------------------------------------------
    # Public log methods
    # ------------------------------------------------------------------

    def log_backup_created(self, table: str, backup_name: str, record_count: int):
        self._record("backup_events", {
            "timestamp": datetime.now().isoformat(),
            "type": "backup_created",
            "table": table,
            "backup_name": backup_name,
            "record_count": record_count,
            "severity": "INFO",
        })

    def log_restore_complete(self, timestamp: str, restored_tables: List[str]):
        self._record("restore_events", {
            "timestamp": datetime.now().isoformat(),
            "type": "restore_complete",
            "restore_timestamp": timestamp,
            "restored_tables": restored_tables,
            "severity": "INFO",
        })

    def log_verification_failure(self, table: str, before: int, after: int):
        self._record("verification_failures", {
            "timestamp": datetime.now().isoformat(),
            "type": "verification_failure",
            "table": table,
            "before_count": before,
            "after_count": after,
            "difference": after - before,
            "severity": "HIGH",
        })

    def log_orphaned_record(self, table: str, record_id: Any, fk_col: str, fk_value: Any):
        self._record("orphaned_records", {
            "timestamp": datetime.now().isoformat(),
            "type": "orphaned_record",
            "table": table,
            "record_id": str(record_id),
            "missing_foreign_key": fk_col,
            "missing_value": str(fk_value),
            "severity": "HIGH",
        })

    def log_foreign_key_violation(self, table: str, record_id: Any, constraint: str, details: str):
        self._record("foreign_key_violations", {
            "timestamp": datetime.now().isoformat(),
            "type": "foreign_key_violation",
            "table": table,
            "record_id": str(record_id),
            "constraint": constraint,
            "details": details[:500],
            "severity": "HIGH",
        })

    def log_null_value(self, table: str, record_id: Any, column: str, severity: str = "MEDIUM"):
        self._record("null_values", {
            "timestamp": datetime.now().isoformat(),
            "type": "null_value",
            "table": table,
            "record_id": str(record_id),
            "column": column,
            "severity": severity,
        })

    def log_duplicate_key(self, table: str, key_col: str, key_value: Any, count: int):
        self._record("duplicate_keys", {
            "timestamp": datetime.now().isoformat(),
            "type": "duplicate_key",
            "table": table,
            "key_column": key_col,
            "key_value": str(key_value),
            "duplicate_count": count,
            "severity": "MEDIUM",
        })

    def log_schema_mismatch(self, table: str, source_cols: List[str], target_cols: List[str]):
        self._record("schema_mismatches", {
            "timestamp": datetime.now().isoformat(),
            "type": "schema_mismatch",
            "table": table,
            "source_columns": source_cols,
            "target_columns": target_cols,
            "missing_in_source": [c for c in target_cols if c not in source_cols],
            "extra_in_source":   [c for c in source_cols if c not in target_cols],
            "severity": "HIGH",
        })

    def log_batch_error(self, table: str, batch_start: int, batch_end: int,
                        error_message: str, sample_rows: List = None):
        self._record("batch_errors", {
            "timestamp": datetime.now().isoformat(),
            "type": "batch_error",
            "table": table,
            "batch_range": f"{batch_start}-{batch_end}",
            "error_message": error_message[:500],
            "sample_rows": (sample_rows[:3] if sample_rows else None),
            "severity": "HIGH",
        })

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.mismatches.items()}

    def generate_report(self) -> str:
        lines = [
            "",
            "=" * 70,
            "DATA MISMATCH REPORT",
            f"Generated: {datetime.now().isoformat()}",
            "=" * 70,
            "",
            "SUMMARY:",
        ]
        summary = self.get_summary()
        label_map = {
            "orphaned_records":       "Orphaned Records",
            "foreign_key_violations": "FK Violations",
            "null_values":            "Null Values",
            "duplicate_keys":         "Duplicate Keys",
            "type_mismatches":        "Type Mismatches",
            "schema_mismatches":      "Schema Mismatches",
            "batch_errors":           "Batch Errors",
            "backup_events":          "Backup Events",
            "restore_events":         "Restore Events",
            "verification_failures":  "Verification Failures",
        }
        for key, label in label_map.items():
            lines.append(f"  {label:<28} {summary[key]}")

        for section, header in (
            ("orphaned_records",       "ORPHANED RECORDS"),
            ("foreign_key_violations", "FOREIGN KEY VIOLATIONS"),
            ("schema_mismatches",      "SCHEMA MISMATCHES"),
            ("batch_errors",           "BATCH ERRORS"),
        ):
            items = self.mismatches.get(section, [])
            if not items:
                continue
            lines += ["", "-" * 50, header, "-" * 50]
            for item in items[:20]:
                lines.append(f"  {json.dumps(item, default=self._serialise)}")
            if len(items) > 20:
                lines.append(f"  ... and {len(items) - 20} more")

        lines += ["", "=" * 70, "END OF REPORT", "=" * 70]
        return "\n".join(lines)

    def save_report(self, filename: str = None) -> str:
        if filename is None:
            filename = f"mismatch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.log_dir, filename)
        with open(path, "w") as fh:
            json.dump(self.mismatches, fh, indent=2, default=self._serialise)
        return path


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
_instance: DataMismatchLogger = None
_instance_lock = threading.Lock()


def get_mismatch_logger() -> DataMismatchLogger:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DataMismatchLogger()
    return _instance


def reset_mismatch_logger():
    """Call at the start of each new migration run to get a fresh logger."""
    global _instance
    with _instance_lock:
        _instance = DataMismatchLogger()
    return _instance
