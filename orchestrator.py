"""
ORCHESTRATOR
Coordinates all agents with FK chain tracking.
CrewAI result is consumed as a plain string (no .get() call on CrewOutput).
"""

import json
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from psycopg2.extras import execute_values
import psycopg2

from agents.data_mismatch_logger import get_mismatch_logger, reset_mismatch_logger
from agents.data_quality_agent import DataQualityAgent
from agents.extraction_agent import extract_all_data
from agents.transformation_agent import transform_all_data
from agents.validation_agent import validate_data
from agents.anomaly_agent import detect_anomalies
from config.schema_mapping import get_default_mapping
from crew_collaboration import CrewAICollaboration
from db_config import get_target_connection
from langgraph_workflow import LangGraphWorkflow

load_dotenv()

# ------------------------------------------------------------
# LANGCHAIN TOOLS
# ------------------------------------------------------------


@tool
def analyze_data_volume(estimated_rows: int) -> str:
    """Analyse data volume and recommend batch size and thread count."""
    if estimated_rows < 10_000:
        return json.dumps({"batch_size": estimated_rows, "threads": 1})
    if estimated_rows < 100_000:
        return json.dumps({"batch_size": 10_000, "threads": 2})
    return json.dumps({"batch_size": 50_000, "threads": 4})


@tool
def estimate_migration_time(rows: int, batch_size: int) -> str:
    """Estimate total migration wall-clock time given row count and batch size."""
    batches = (rows + batch_size - 1) // batch_size
    seconds = batches * 2
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        label = f"{hours}h {mins}m"
    elif minutes:
        label = f"{minutes}m"
    else:
        label = f"{seconds}s"
    return json.dumps({"estimated_time": label, "batches": batches})


@tool
def check_data_quality_risks() -> str:
    """Return common data quality risks for a core banking migration."""
    return json.dumps({
        "risks": [
            "Null CustomerId / AccountNumber violates FK constraints",
            "Orphaned transactions referencing non-existent accounts",
            "Negative account balances",
            "Duplicate BVN / NationalID",
        ],
        "recommendation": "Validate identity columns before load",
    })


# ------------------------------------------------------------
# LANGCHAIN AGENT
# ------------------------------------------------------------


class LangChainAIAgent:
    def __init__(self):
        self.llm = ChatGroq(
            temperature=0.3,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant",
        )
        self.tools = [
            analyze_data_volume,
            estimate_migration_time,
            check_data_quality_risks,
        ]
        self.executor = create_react_agent(
            self.llm,
            self.tools,
            prompt=(
                "You are a Senior Banking Data Migration Architect. "
                "Always call the available tools before giving a recommendation. "
                "Return your final answer as a JSON object with keys: "
                "batch_size, threads, estimated_time, risk_level (1-10), recommendation."
            ),
        )
        self.decision_history = []

    def plan_migration(self, estimated_rows: int) -> dict:
        task = (
            f"Plan the migration of {estimated_rows:,} banking records. "
            "1. Analyse volume and recommend batch_size and threads. "
            "2. Estimate migration time. "
            "3. Identify the top data quality risks. "
            "Return a JSON object: batch_size, threads, estimated_time, risk_level, recommendation."
        )
        result = self.executor.invoke(
            {"messages": [{"role": "user", "content": task}]})
        plan_text = result["messages"][-1].content
        entry = {
            "timestamp": datetime.now().isoformat(),
            "estimated_rows": estimated_rows,
            "agent_plan": plan_text,
            "tools_used": [t.name for t in self.tools],
        }
        self.decision_history.append(entry)
        return entry

    def get_summary(self) -> dict:
        return {
            "decisions_made": len(self.decision_history),
            "latest_plan": self.decision_history[-1] if self.decision_history else None,
        }


# ------------------------------------------------------------
# ORCHESTRATOR
# ------------------------------------------------------------


class Orchestrator:
    def __init__(
        self,
        schema_mapping=None,
        progress_callback=None,
        estimated_rows=1_000_000,
        run_data_quality=True,
    ):
        self.schema_mapping = schema_mapping or get_default_mapping()
        self.progress_callback = progress_callback
        self.estimated_rows = estimated_rows
        self.run_data_quality = run_data_quality

        reset_mismatch_logger()
        self.mismatch_logger = get_mismatch_logger()

        self.langchain_agent = None
        self.crew_collaboration = None
        self.quality_agent = None

        self.results = {
            "status": "started",
            "start_time": None,
            "end_time": None,
            "data_quality_summary": {},
            "langchain_decisions": {},
            "crewai_result": None,
            "crewai_error": None,
            "langgraph_state": None,
            "extracted": {},
            "transformed": {},
            "validation_passed": False,
            "validation_issues": {},
            "anomalies": {},
            "loaded": {},
        }

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> bool:
        self.results["start_time"] = datetime.now().isoformat()

        # Step 0: Data Quality
        if self.run_data_quality:
            self._run_data_quality()

        # Step 1: LangChain planning
        print("\n" + "=" * 60)
        print("LANGCHAIN AGENT: MIGRATION PLANNING")
        print("=" * 60)
        try:
            self.langchain_agent = LangChainAIAgent()
            plan = self.langchain_agent.plan_migration(self.estimated_rows)
            self.results["langchain_decisions"] = plan
            print(f"Plan: {plan['agent_plan'][:300]}")

            match = re.search(r'"batch_size"\s*:\s*(\d+)', plan["agent_plan"])
            if match:
                self.schema_mapping["batch_size"] = int(match.group(1))
                print(
                    f"Batch size updated to: {self.schema_mapping['batch_size']:,}")
        except Exception as exc:
            print(f"LangChain error (non-fatal): {exc}")

        # Step 2: CrewAI
        print("\n" + "=" * 60)
        print("CREWAI: MULTI-AGENT COLLABORATION")
        print("=" * 60)
        try:
            self.crew_collaboration = CrewAICollaboration()
            # run_collaboration now returns a plain str (or None), never a CrewOutput
            result, _ = self.crew_collaboration.run_collaboration(
                {"total_records": self.estimated_rows}
            )
            # result is already a str; slice directly, no .get() needed
            self.results["crewai_result"] = result[:5000] if result else None
        except Exception as exc:
            self.results["crewai_error"] = str(exc)[:500]
            print(f"CrewAI error (non-fatal): {exc}")

        # Step 3: LangGraph state initialise
        print("\n" + "=" * 60)
        print("LANGGRAPH: WORKFLOW STATE MACHINE INITIALISED")
        print("=" * 60)
        lg_state = {
            "status": "TRACKING",
            "extracted_records": 0,
            "transformed_records": 0,
            "loaded_records": 0,
            "anomalies": [],
            "validation_passed": True,
            "errors": [],
            "current_step": "pending",
        }
        self.results["langgraph_state"] = lg_state

        # Step 4: Extract
        print("\n" + "=" * 60)
        print("EXTRACTION AGENT: READING SOURCE DATA")
        print("=" * 60)
        extracted = extract_all_data(self.schema_mapping, self._progress)
        self.results["extracted"] = {
            k: len(v) for k, v in extracted.items() if v is not None
        }
        lg_state["extracted_records"] = sum(self.results["extracted"].values())
        lg_state["current_step"] = "extract"

        # Step 5: Transform
        print("\n" + "=" * 60)
        print("TRANSFORMATION AGENT: CONVERTING SCHEMAS")
        print("=" * 60)
        transformed = transform_all_data(
            extracted, self.schema_mapping, self._progress)
        self.results["transformed"] = {
            k: len(v) for k, v in transformed.items() if v is not None
        }
        lg_state["transformed_records"] = sum(
            self.results["transformed"].values())
        lg_state["current_step"] = "transform"

        # Step 6: Validate
        print("\n" + "=" * 60)
        print("VALIDATION AGENT: CHECKING INTEGRITY")
        print("=" * 60)
        valid, issues = validate_data(transformed)
        self.results["validation_passed"] = valid
        self.results["validation_issues"] = issues
        lg_state["validation_passed"] = valid

        if not valid:
            self.results["status"] = "aborted_validation_failed"
            lg_state["status"] = "FAILED"
            return False

        # Step 7: Anomaly detection
        print("\n" + "=" * 60)
        print("ANOMALY DETECTION AGENT: SCANNING FOR RISKS")
        print("=" * 60)
        anomalies = detect_anomalies(transformed)
        self.results["anomalies"] = anomalies

        # Step 8: Load
        print("\n" + "=" * 60)
        print("LOAD AGENT: WRITING TO TARGET DATABASE")
        print("=" * 60)
        load_results = self._bulk_load(transformed)
        self.results["loaded"] = load_results

        lg_state["loaded_records"] = sum(load_results.values())
        lg_state["current_step"] = "load"
        lg_state["status"] = "COMPLETED"

        self.results["end_time"] = datetime.now().isoformat()
        self.results["status"] = "completed"
        self._save_results()
        self._print_summary(valid, anomalies, load_results)

        return True

    # ------------------------------------------------------------------
    # Data Quality
    # ------------------------------------------------------------------

    def _run_data_quality(self):
        print("\n" + "=" * 60)
        print("DATA QUALITY AGENT: PRE-MIGRATION SCAN")
        print("=" * 60)

        self.quality_agent = DataQualityAgent()
        self.quality_agent.run_full_scan()
        print(self.quality_agent.get_report())

        self.results["data_quality_summary"] = {
            "orphaned_records": len(self.quality_agent.issues.get("orphaned_records", {})),
            "duplicates": len(self.quality_agent.issues.get("duplicates", {})),
            "null_values": len(self.quality_agent.issues.get("null_values", {})),
            "negative_balances": 1 if self.quality_agent.issues.get("negative_balances") else 0,
        }

        if any(self.results["data_quality_summary"].values()):
            print("\n" + "=" * 60)
            print("DATA QUALITY AGENT: AUTO-REPAIR IN PROGRESS")
            print("=" * 60)
            self.quality_agent.auto_repair()

            self.quality_agent.issues = {}
            self.quality_agent.run_full_scan()
            if self.quality_agent.issues:
                print("\nWARNING: Some issues could not be automatically resolved.")
            else:
                print("\nAll data quality issues resolved.")

    # ------------------------------------------------------------------
    # Bulk load with FK chain tracking
    # ------------------------------------------------------------------

    def _bulk_load(self, transformed_data: dict) -> dict:
        load_results = {}
        insert_order = self.schema_mapping.get(
            "insert_order", list(transformed_data.keys())
        )
        batch_size = self.schema_mapping.get("batch_size", 50_000)

        valid_customer_ids: set = set()
        valid_account_numbers: set = set()

        conn = get_target_connection()
        cursor = conn.cursor()

        try:
            for table_name in insert_order:
                if table_name not in transformed_data:
                    continue
                df = transformed_data[table_name]
                if df is None or df.empty:
                    load_results[table_name] = 0
                    continue

                target_table = self.schema_mapping["tables"][table_name]["target_table"]
                cols = self._resolve_columns(table_name, df)

                if not cols:
                    print(
                        f"  ERROR: no columns resolved for '{table_name}' -- skipping")
                    load_results[table_name] = 0
                    continue

                # FK pre-filtering
                if table_name == "accounts" and valid_customer_ids and "CustomerId" in df.columns:
                    before = len(df)
                    df = df[df["CustomerId"].isin(valid_customer_ids)].copy()
                    skipped = before - len(df)
                    if skipped:
                        print(
                            f"  Filtered {skipped:,} accounts (CustomerId not in Customers)")
                        self.mismatch_logger.log_orphaned_record(
                            "accounts", "batch", "CustomerId",
                            f"{skipped} records filtered",
                        )

                if table_name == "transactions" and valid_account_numbers and "AccountNumber" in df.columns:
                    before = len(df)
                    df = df[df["AccountNumber"].isin(
                        valid_account_numbers)].copy()
                    skipped = before - len(df)
                    if skipped:
                        print(
                            f"  Filtered {skipped:,} transactions (AccountNumber not in Accounts)")
                        self.mismatch_logger.log_orphaned_record(
                            "transactions", "batch", "AccountNumber",
                            f"{skipped} records filtered",
                        )

                if table_name == "loans" and valid_customer_ids and "CustomerId" in df.columns:
                    before = len(df)
                    df = df[df["CustomerId"].isin(valid_customer_ids)].copy()
                    skipped = before - len(df)
                    if skipped:
                        print(
                            f"  Filtered {skipped:,} loans (CustomerId not in Customers)")
                        self.mismatch_logger.log_orphaned_record(
                            "loans", "batch", "CustomerId",
                            f"{skipped} records filtered",
                        )

                print(
                    f"  Loading {len(df):,} records into {target_table} ({len(cols)} cols)")
                loaded = self._insert_batches(
                    conn, cursor, df, target_table, cols, batch_size, table_name
                )
                load_results[table_name] = loaded
                print(f"  Loaded {loaded:,} / {len(df):,} into {target_table}")

                # Track valid IDs after successful load
                if table_name == "customers" and "CustomerId" in df.columns:
                    valid_customer_ids.update(
                        df["CustomerId"].dropna().tolist())

                if table_name == "accounts" and "AccountNumber" in df.columns:
                    valid_account_numbers.update(
                        df["AccountNumber"].dropna().tolist())

                # Update LangGraph state
                lg_state = self.results.get("langgraph_state")
                if isinstance(lg_state, dict):
                    lg_state["loaded_records"] = sum(load_results.values())

        finally:
            cursor.close()
            conn.close()

        return load_results

    def _insert_batches(
        self, conn, cursor, df, target_table, cols, batch_size, table_name
    ) -> int:
        loaded = 0
        total = len(df)

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = df.iloc[start:end]
            rows = [tuple(row[c] for c in cols) for _, row in batch.iterrows()]

            if not rows:
                continue

            sql = (
                f"INSERT INTO {target_table} ({', '.join(cols)}) "
                f"VALUES %s ON CONFLICT DO NOTHING"
            )

            try:
                execute_values(cursor, sql, rows)
                conn.commit()
                loaded += len(rows)
                if self.progress_callback:
                    self.progress_callback("load", table_name, loaded, total)

            except Exception as exc:
                conn.rollback()
                err_str = str(exc)
                self.mismatch_logger.log_batch_error(
                    table_name, start, end, err_str, rows[:3]
                )
                print(f"    Batch error ({start}-{end}): {err_str[:120]}")

                # Row-by-row fallback with a fresh cursor
                cursor.close()
                cursor = conn.cursor()
                row_sql = (
                    f"INSERT INTO {target_table} ({', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING"
                )
                for row in rows:
                    try:
                        cursor.execute(row_sql, row)
                        conn.commit()
                        loaded += 1
                    except psycopg2.Error as row_exc:
                        conn.rollback()
                        if "foreign key" in str(row_exc).lower():
                            self.mismatch_logger.log_foreign_key_violation(
                                table_name,
                                row[0] if row else "unknown",
                                "FK constraint",
                                str(row_exc)[:200],
                            )

        return loaded

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _resolve_columns(self, table_name: str, df) -> list:
        target_cols = list(
            self.schema_mapping["tables"][table_name]["columns"].values()
        )
        matched = [c for c in target_cols if c in df.columns]
        if not matched:
            self.mismatch_logger.log_schema_mismatch(
                table_name, list(df.columns), target_cols
            )
            return list(df.columns)
        return matched

    def _progress(self, step, table, current, total=None):
        if self.progress_callback:
            self.progress_callback(step, table, current, total)

    def _save_results(self):
        os.makedirs("reports", exist_ok=True)
        path = "reports/migration_results.json"
        with open(path, "w") as fh:
            json.dump(self.results, fh, indent=2, default=str)
        print(f"\nResults saved to {path}")

    def _print_summary(self, valid, anomalies, load_results):
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(
            f"LangChain Agent      : {'ACTIVE' if self.langchain_agent else 'INACTIVE'}")
        print(
            f"CrewAI Collaboration : {'ACTIVE' if self.crew_collaboration else 'INACTIVE'}")
        print(f"LangGraph Workflow   : ACTIVE")
        print(f"Total Records Loaded : {sum(load_results.values()):,}")
        print(f"Validation           : {'PASSED' if valid else 'FAILED'}")
        print(f"Anomaly Types Found  : {len(anomalies)}")

        summary = self.mismatch_logger.get_summary()
        if any(v for k, v in summary.items()
               if k not in ("backup_events", "restore_events")):
            print("\nData Mismatch Summary:")
            for k, v in summary.items():
                if v and k not in ("backup_events", "restore_events"):
                    print(f"  {k}: {v}")
        print("=" * 60)
