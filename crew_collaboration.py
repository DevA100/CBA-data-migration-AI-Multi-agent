"""
CREWAI MULTI-AGENT COLLABORATION
crewai 0.28.x Agent.llm accepts a plain string model identifier.
API key is set in the environment before agents are created.
Telemetry disabled to suppress call_llm_and_parse listener warnings.
"""

import os

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
import groq_patch

from datetime import datetime

from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv

load_dotenv()

# crewai 0.28.x reads these env vars internally when llm is a string
os.environ["OPENAI_API_KEY"] = os.getenv("GROQ_API_KEY", "")
os.environ["OPENAI_API_BASE"] = "https://api.groq.com/openai/v1"

_MODEL = "groq/llama-3.1-8b-instant"


def _extract_crew_text(result) -> str:
    """
    Safely convert a crew.kickoff() return value to a plain string.
    crewai 0.28.x returns a plain str.
    On internal failure the object can evaluate to a bool-like value.
    """
    if result is None or isinstance(result, bool):
        return None
    if hasattr(result, "raw"):
        return result.raw
    if hasattr(result, "output"):
        return str(result.output)
    return str(result)


class CrewAICollaboration:
    def __init__(self):
        self.collaboration_history = []

    def run_collaboration(self, context: dict = None):
        print("CrewAI: Extraction Expert | Validation Specialist | Risk Assessor")

        extraction_agent = Agent(
            role="Extraction Strategy Expert",
            goal="Design an optimal extraction plan for a large-scale banking migration.",
            backstory=(
                "A senior database architect with 15 years of experience extracting "
                "large volumes from PostgreSQL banking systems under strict SLA windows."
            ),
            llm=_MODEL,
            verbose=False,
            allow_delegation=False,
        )

        validation_agent = Agent(
            role="Data Integrity Specialist",
            goal="Define the validation strategy that prevents corrupt records entering the target system.",
            backstory=(
                "A data quality engineer specialising in financial data compliance, "
                "IFRS 9 reporting, and core banking reconciliation."
            ),
            llm=_MODEL,
            verbose=False,
            allow_delegation=False,
        )

        risk_agent = Agent(
            role="Migration Risk Assessor",
            goal="Identify migration risks and provide a go/no-go recommendation.",
            backstory=(
                "A principal consultant who has overseen 40 core banking platform "
                "migrations and writes risk frameworks for central banks."
            ),
            llm=_MODEL,
            verbose=False,
            allow_delegation=False,
        )

        total = context.get(
            "total_records", 1_000_000) if context else 1_000_000

        extraction_task = Task(
            description=(
                f"Create an extraction plan for {total:,} banking records. "
                "Return batch_size, parallel_workers, estimated_minutes, and bottlenecks."
            ),
            agent=extraction_agent,
            expected_output="JSON with batch_size, parallel_workers, estimated_minutes, bottlenecks",
        )

        validation_task = Task(
            description=(
                "Using the extraction plan, define the validation strategy: "
                "critical columns that must not be null, referential integrity checks, "
                "and sampling strategy for large tables."
            ),
            agent=validation_agent,
            expected_output="Structured validation strategy document",
            context=[extraction_task],
        )

        risk_task = Task(
            description=(
                "Based on the extraction plan and validation strategy provide: "
                "1. Overall risk level: Low / Medium / High. "
                "2. Top 3 risks with mitigations. "
                "3. Go / No-Go recommendation with conditions."
            ),
            agent=risk_agent,
            expected_output="Risk assessment with go/no-go recommendation",
            context=[extraction_task, validation_task],
        )

        crew = Crew(
            agents=[extraction_agent, validation_agent, risk_agent],
            tasks=[extraction_task, validation_task, risk_task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            raw_result = crew.kickoff()
            text = _extract_crew_text(raw_result)

            self.collaboration_history.append({
                "timestamp": datetime.now().isoformat(),
                "result": text,
            })
            return text, self.collaboration_history

        except Exception as exc:
            print(f"CrewAI error: {exc}")
            self.collaboration_history.append({
                "timestamp": datetime.now().isoformat(),
                "result": None,
                "error": str(exc)[:500],
            })
            return None, self.collaboration_history
