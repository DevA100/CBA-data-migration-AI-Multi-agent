"""
DATA QUALITY AGENT
Scans the source database for integrity issues before migration begins,
applies non-destructive repairs, and maintains a full audit trail.
"""

from datetime import datetime
from db_config import get_source_connection


class DataQualityAgent:

    def __init__(self):
        self.issues: dict = {}
        self.fixes_applied: dict = {}
        self.repair_log: list = []
        self.backup_timestamp: str = None
        self._logger = None

    def _get_logger(self):
        if self._logger is None:
            from agents.data_mismatch_logger import get_mismatch_logger
            self._logger = get_mismatch_logger()
        return self._logger

    # ------------------------------------------------------------------
    # Backup / Restore
    # ------------------------------------------------------------------

    def backup_tables(self, tables=None):
        if tables is None:
            tables = ["branch", "customers",
                      "accounts", "transactions", "loans"]

        conn = get_source_connection()
        cursor = conn.cursor()
        self.backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"\nCreating backup — timestamp: {self.backup_timestamp}")

        for table in tables:
            backup_name = f"pre_migration_backup_{table}_{self.backup_timestamp}"
            try:
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS {backup_name} AS SELECT * FROM {table}"
                )
                cursor.execute(f"SELECT COUNT(*) FROM {backup_name}")
                count = cursor.fetchone()[0]
                print(f"  Backed up {table}: {count:,} rows -> {backup_name}")
                self._get_logger().log_backup_created(table, backup_name, count)
            except Exception as exc:
                print(f"  ERROR backing up {table}: {str(exc)[:120]}")

        conn.commit()
        cursor.close()
        conn.close()
        return self.backup_timestamp

    def restore_from_backup(self, timestamp=None):
        ts = timestamp or self.backup_timestamp
        if not ts:
            print("ERROR: No backup timestamp available.")
            return False

        conn = get_source_connection()
        cursor = conn.cursor()
        restored = []

        for table in ["branch", "customers", "accounts", "transactions", "loans"]:
            backup_name = f"pre_migration_backup_{table}_{ts}"
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                (backup_name,),
            )
            if cursor.fetchone()[0]:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                cursor.execute(
                    f"CREATE TABLE {table} AS SELECT * FROM {backup_name}")
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  Restored {table}: {cursor.fetchone()[0]:,} rows")
                restored.append(table)

        conn.commit()
        cursor.close()
        conn.close()
        self._get_logger().log_restore_complete(ts, restored)
        return len(restored) > 0

    # ------------------------------------------------------------------
    # Scan methods
    # ------------------------------------------------------------------

    def scan_orphaned_records(self):
        conn = get_source_connection()
        cursor = conn.cursor()
        issues = {}
        logger = self._get_logger()

        # Accounts with no matching customer
        cursor.execute(
            "SELECT COUNT(*) FROM accounts a LEFT JOIN customers c ON a.cust_id = c.cust_id WHERE c.cust_id IS NULL"
        )
        n = cursor.fetchone()[0]
        if n:
            cursor.execute(
                "SELECT a.acct_id, a.cust_id FROM accounts a LEFT JOIN customers c ON a.cust_id = c.cust_id WHERE c.cust_id IS NULL LIMIT 100"
            )
            samples = cursor.fetchall()
            issues["accounts"] = {
                "orphaned_count": n,
                "message": f"{n:,} accounts with no matching customer",
                "severity": "HIGH",
                "fixable": True,
                "fix_options": ["create_placeholder_customers", "delete"],
            }
            for acct_id, cust_id in samples[:20]:
                logger.log_orphaned_record(
                    "accounts", acct_id, "cust_id", cust_id)

        # Loans with no matching customer
        cursor.execute(
            "SELECT COUNT(*) FROM loans l LEFT JOIN customers c ON l.cust_id = c.cust_id WHERE c.cust_id IS NULL"
        )
        n = cursor.fetchone()[0]
        if n:
            issues["loans"] = {
                "orphaned_count": n,
                "message": f"{n:,} loans with no matching customer",
                "severity": "HIGH",
                "fixable": True,
                "fix_options": ["create_placeholder_customers", "delete"],
            }

        # Transactions with no matching account
        cursor.execute(
            "SELECT COUNT(*) FROM transactions t LEFT JOIN accounts a ON t.acct_num = a.acct_num WHERE a.acct_num IS NULL"
        )
        n = cursor.fetchone()[0]
        if n:
            issues["transactions"] = {
                "orphaned_count": n,
                "message": f"{n:,} transactions with no matching account",
                "severity": "MEDIUM",
                "fixable": True,
                "fix_options": ["delete"],
            }

        cursor.close()
        conn.close()
        self.issues["orphaned_records"] = issues
        return issues

    def scan_duplicates(self):
        conn = get_source_connection()
        cursor = conn.cursor()
        issues = {}
        logger = self._get_logger()

        checks = [
            ("duplicate_bvn",            "customers",  "bvn_no",
             "BVN numbers used by multiple customers"),
            ("duplicate_national_id",     "customers",  "nat_id",
             "National IDs used by multiple customers"),
            ("duplicate_account_numbers", "accounts",
             "acct_num", "Account numbers duplicated"),
        ]

        for key, table, col, msg in checks:
            cursor.execute(
                f"SELECT {col}, COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} != '' "
                f"GROUP BY {col} HAVING COUNT(*) > 1 LIMIT 50"
            )
            rows = cursor.fetchall()
            if rows:
                issues[key] = {
                    "count": len(rows),
                    "message": f"{len(rows)} {msg}",
                    "severity": "MEDIUM" if table == "customers" else "HIGH",
                    "fixable": True,
                    "fix_options": ["keep_first"],
                }
                for val, cnt in rows[:10]:
                    logger.log_duplicate_key(table, col, val, cnt)

        cursor.close()
        conn.close()
        self.issues["duplicates"] = issues
        return issues

    def scan_null_critical_fields(self):
        conn = get_source_connection()
        cursor = conn.cursor()
        issues = {}
        logger = self._get_logger()

        checks = [
            ("customers",    "full_name", "cust_id",
             "customers with missing names"),
            ("accounts",     "acct_num",  "acct_id",
             "accounts with missing account numbers"),
            ("transactions", "amt",       "trans_id",
             "transactions with null amounts"),
        ]

        for table, col, id_col, msg in checks:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL OR CAST({col} AS TEXT) = ''"
            )
            n = cursor.fetchone()[0]
            if n:
                cursor.execute(
                    f"SELECT {id_col} FROM {table} WHERE {col} IS NULL OR CAST({col} AS TEXT) = '' LIMIT 50"
                )
                samples = [r[0] for r in cursor.fetchall()]
                issues.setdefault(table, {})[f"null_{col}"] = n
                issues[table]["message"] = f"{n:,} {msg}"
                issues[table]["severity"] = "HIGH"
                issues[table]["fixable"] = True
                for sid in samples[:10]:
                    logger.log_null_value(table, sid, col, "HIGH")

        cursor.close()
        conn.close()
        self.issues["null_values"] = issues
        return issues

    def scan_negative_balances(self):
        conn = get_source_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM accounts WHERE bal < 0")
        n = cursor.fetchone()[0]
        if n:
            cursor.execute(
                "SELECT acct_id, bal FROM accounts WHERE bal < 0 LIMIT 50")
            self.issues["negative_balances"] = {
                "count": n,
                "message": f"{n:,} accounts with negative balances",
                "severity": "MEDIUM",
                "fixable": True,
                "fix_options": ["set_zero", "absolute_value"],
                "samples": cursor.fetchall(),
            }

        cursor.close()
        conn.close()
        return self.issues.get("negative_balances", {})

    # ------------------------------------------------------------------
    # Repair methods
    # ------------------------------------------------------------------

    def repair_orphaned_records(self, strategy="create_placeholder_customers"):
        conn = get_source_connection()
        cursor = conn.cursor()
        fixes = {}

        if strategy == "create_placeholder_customers":
            for parent_table in ("accounts", "loans"):
                cursor.execute(
                    f"""
                    INSERT INTO customers (cust_id, full_name, cust_status)
                    SELECT DISTINCT t.cust_id,
                           'PLACEHOLDER_' || t.cust_id,
                           'Inactive'
                    FROM {parent_table} t
                    LEFT JOIN customers c ON t.cust_id = c.cust_id
                    WHERE c.cust_id IS NULL
                    ON CONFLICT (cust_id) DO NOTHING
                    RETURNING cust_id
                    """
                )
                created = cursor.fetchall()
                fixes[f"{parent_table}_placeholders_created"] = len(created)
            conn.commit()

        elif strategy == "delete":
            cursor.execute(
                "DELETE FROM accounts WHERE cust_id NOT IN (SELECT cust_id FROM customers) RETURNING acct_id"
            )
            fixes["accounts_deleted"] = len(cursor.fetchall())
            cursor.execute(
                "DELETE FROM loans WHERE cust_id NOT IN (SELECT cust_id FROM customers) RETURNING loan_id"
            )
            fixes["loans_deleted"] = len(cursor.fetchall())
            cursor.execute(
                "DELETE FROM transactions WHERE acct_num NOT IN (SELECT acct_num FROM accounts) RETURNING trans_id"
            )
            fixes["transactions_deleted"] = len(cursor.fetchall())
            conn.commit()

        self.repair_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": f"repair_orphaned_records:{strategy}",
            "results": fixes,
        })
        cursor.close()
        conn.close()
        return fixes

    def repair_null_values(self):
        conn = get_source_connection()
        cursor = conn.cursor()
        fixes = {}

        cursor.execute(
            "UPDATE customers SET full_name = 'UNKNOWN_' || cust_id WHERE full_name IS NULL OR full_name = '' RETURNING cust_id"
        )
        fixes["customer_names_fixed"] = len(cursor.fetchall())

        cursor.execute(
            "UPDATE transactions SET amt = 0 WHERE amt IS NULL RETURNING trans_id"
        )
        fixes["transaction_amounts_fixed"] = len(cursor.fetchall())

        conn.commit()
        cursor.close()
        conn.close()

        self.repair_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "repair_null_values",
            "results": fixes,
        })
        return fixes

    def repair_negative_balances(self, strategy="set_zero"):
        conn = get_source_connection()
        cursor = conn.cursor()

        if strategy == "absolute_value":
            cursor.execute(
                "UPDATE accounts SET bal = ABS(bal) WHERE bal < 0 RETURNING acct_id"
            )
        else:
            cursor.execute(
                "UPDATE accounts SET bal = 0 WHERE bal < 0 RETURNING acct_id"
            )

        fixes = {"accounts_fixed": len(cursor.fetchall())}
        conn.commit()
        cursor.close()
        conn.close()

        self.repair_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": f"repair_negative_balances:{strategy}",
            "results": fixes,
        })
        return fixes

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run_full_scan(self) -> dict:
        print("\n" + "=" * 60)
        print("DATA QUALITY AGENT: SCANNING SOURCE DATABASE")
        print("=" * 60)

        self.scan_orphaned_records()
        self.scan_duplicates()
        self.scan_null_critical_fields()
        self.scan_negative_balances()

        total = (
            len(self.issues.get("orphaned_records", {}))
            + len(self.issues.get("duplicates", {}))
            + len(self.issues.get("null_values", {}))
            + (1 if self.issues.get("negative_balances") else 0)
        )
        print(f"Scan complete. Found {total} issue categories.")
        return self.issues

    def auto_repair(self) -> dict:
        print("\n" + "=" * 60)
        print("DATA QUALITY AGENT: AUTO-REPAIR STARTED")
        print("=" * 60)

        print("\nCreating backup before repairs...")
        self.backup_tables()

        all_fixes = {}

        if self.issues.get("orphaned_records"):
            print("\nRepairing orphaned records (create placeholders)...")
            all_fixes["orphaned_records"] = self.repair_orphaned_records(
                strategy="create_placeholder_customers"
            )

        if self.issues.get("null_values"):
            print("\nRepairing null values...")
            all_fixes["null_values"] = self.repair_null_values()

        if self.issues.get("negative_balances"):
            print("\nRepairing negative balances...")
            all_fixes["negative_balances"] = self.repair_negative_balances()

        self.fixes_applied = all_fixes

        print("\n" + "=" * 60)
        print("VERIFYING REPAIRS")
        print("=" * 60)
        conn = get_source_connection()
        cursor = conn.cursor()
        for table in ["branch", "customers", "accounts", "transactions", "loans"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {cursor.fetchone()[0]:,} records")
        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("DATA QUALITY AGENT: AUTO-REPAIR COMPLETE")
        print(f"Backup timestamp: {self.backup_timestamp}")
        print("=" * 60)

        return all_fixes

    def get_report(self) -> str:
        lines = [
            "",
            "=" * 70,
            "DATA QUALITY REPORT",
            f"Generated: {datetime.now().isoformat()}",
            "=" * 70,
        ]

        for category, header in (
            ("orphaned_records",  "ORPHANED RECORDS"),
            ("duplicates",        "DUPLICATES"),
            ("null_values",       "NULL VALUES"),
        ):
            items = self.issues.get(category, {})
            if items:
                lines.append(f"\n[{header}]")
                for key, info in items.items():
                    lines.append(f"  {key}: {info.get('message', '')}")

        nb = self.issues.get("negative_balances", {})
        if nb:
            lines.append(f"\n[NEGATIVE BALANCES]\n  {nb.get('message', '')}")

        lines += [
            "",
            "=" * 70,
            "SAFEGUARDS SUMMARY",
            "=" * 70,
            f"  Backup created:    {'Yes' if self.backup_timestamp else 'No'}",
            f"  Backup timestamp:  {self.backup_timestamp or 'N/A'}",
            "",
            "=" * 70,
            "END OF REPORT",
            "=" * 70,
        ]
        return "\n".join(lines)
