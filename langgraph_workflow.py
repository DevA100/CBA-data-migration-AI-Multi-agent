"""
LANGGRAPH WORKFLOW
State machine that tracks migration progress through extract, transform, and load phases.
"""

from typing import TypedDict, List
from datetime import datetime


class MigrationState(TypedDict):
    status: str
    extracted_records: int
    transformed_records: int
    loaded_records: int
    anomalies: List[str]
    validation_passed: bool
    errors: List[str]
    current_step: str


_STEP_KEY = {
    "extract":   "extracted_records",
    "transform": "transformed_records",
    "load":      "loaded_records",
}


class LangGraphWorkflow:
    """Lightweight state machine; no external LangGraph graph needed for a linear pipeline."""

    def __init__(self):
        self.state_history: list = []

    def run_workflow(self, extraction_func, transform_func, load_func):
        state = self._initial_state()

        for step_name, func in (
            ("extract",   extraction_func),
            ("transform", transform_func),
            ("load",      load_func),
        ):
            state = self._execute_step(state, step_name, func)
            if not state["validation_passed"]:
                state["status"] = "FAILED"
                return state, self.state_history

        state["status"] = "COMPLETED"
        return state, self.state_history

    # ------------------------------------------------------------------

    def _initial_state(self) -> MigrationState:
        return {
            "status": "STARTED",
            "extracted_records": 0,
            "transformed_records": 0,
            "loaded_records": 0,
            "anomalies": [],
            "validation_passed": True,
            "errors": [],
            "current_step": "init",
        }

    def _execute_step(self, state: MigrationState, step_name: str, func) -> MigrationState:
        print(f"\n[LangGraph] Step: {step_name.upper()}")
        state["current_step"] = step_name
        record_key = _STEP_KEY[step_name]

        try:
            result = func()

            if isinstance(result, int):
                state[record_key] = result
            elif isinstance(result, dict):
                state[record_key] = sum(
                    len(v) for v in result.values() if v is not None and hasattr(v, "__len__")
                )
            else:
                state[record_key] = 0

            state["validation_passed"] = True
            print(f"  {step_name} successful — {state[record_key]:,} records")

        except Exception as exc:
            state["validation_passed"] = False
            state["errors"].append(f"{step_name} failed: {str(exc)}")
            print(f"  {step_name} failed: {exc}")

        self.state_history.append({
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "records": state[record_key],
            "validation_passed": state["validation_passed"],
            "errors": list(state["errors"]),
        })

        return state
