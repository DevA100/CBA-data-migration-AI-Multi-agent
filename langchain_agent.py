"""
LANGCHAIN AGENT
Standalone module. The orchestrator imports its own inline version;
this file exists for isolated testing only.
"""

import json
import os

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

load_dotenv()


@tool
def analyze_data_volume(estimated_rows: int) -> str:
    """Analyse data volume and recommend batch size and thread count."""
    if estimated_rows < 10_000:
        return json.dumps({"batch_size": estimated_rows, "threads": 1})
    if estimated_rows < 100_000:
        return json.dumps({"batch_size": 10_000, "threads": 2})
    batches = (estimated_rows + 49_999) // 50_000
    return json.dumps({"batch_size": 50_000, "threads": 4, "batches": batches})


@tool
def estimate_migration_time(rows: int, batch_size: int) -> str:
    """Estimate total migration wall-clock time."""
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
            "Negative account balances may fail target schema CHECK constraints",
            "Duplicate BVN / NationalID across customer records",
            "Invalid date formats in DateOfBirth / TransactionDate columns",
        ],
        "recommendation": "Validate identity columns before load; use ON CONFLICT DO NOTHING.",
    })


class LangChainAgent:

    def __init__(self):
        self.llm = ChatGroq(
            temperature=0.3,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant",
        )
        self.tools = [analyze_data_volume,
                      estimate_migration_time, check_data_quality_risks]
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

    def plan(self, rows: int) -> str:
        result = self.executor.invoke({
            "messages": [{
                "role": "user",
                "content": (
                    f"Plan the migration of {rows:,} banking records. "
                    "Analyse volume, estimate time, and identify the top data quality risks. "
                    "Return a JSON object: batch_size, threads, estimated_time, risk_level, recommendation."
                ),
            }]
        })
        return result["messages"][-1].content


if __name__ == "__main__":
    agent = LangChainAgent()
    print(agent.plan(1_000_000))
