"""Run showcase ingestion and every precomputation stage in order."""
from __future__ import annotations

import subprocess
import sys

PIPELINE_MODULES = (
    "app.ingest_dataset",
    "app.project_person_graph",
    "app.validate_case_scoping",
    "app.project_graphs",
    "app.run_core_algorithms",
    "app.classify_structural_roles",
    "app.compute_criticality",
    "app.detect_financial_patterns",
    "app.case_summaries",
)


def run_pipeline() -> None:
    """Run all stages, stopping immediately if any stage fails."""
    for module in PIPELINE_MODULES:
        subprocess.run([sys.executable, "-m", module], check=True)


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    main()
