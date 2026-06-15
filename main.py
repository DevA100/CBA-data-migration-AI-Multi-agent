"""
Entry point for headless (non-Streamlit) migration runs.
"""

from agents.data_mismatch_logger import get_mismatch_logger
from orchestrator import Orchestrator
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    orch = Orchestrator(run_data_quality=True)
    success = orch.run()

    logger = get_mismatch_logger()
    report_path = logger.save_report()
    print(f"\nMismatch report: {report_path}")

    if success:
        print("\nMigration completed successfully.")
    else:
        print("\nMigration completed with errors. Check reports/ for details.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
