from __future__ import annotations

import subprocess

from app import run_full_analysis


def test_run_pipeline_executes_every_stage_in_order(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr(run_full_analysis.subprocess, "run", fake_run)

    run_full_analysis.run_pipeline()

    assert calls == [
        ([run_full_analysis.sys.executable, "-m", module], True)
        for module in run_full_analysis.PIPELINE_MODULES
    ]
    assert run_full_analysis.PIPELINE_MODULES == (
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


def test_run_pipeline_stops_when_a_stage_fails(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], *, check: bool) -> None:
        module = command[-1]
        calls.append(module)
        if module == "app.project_graphs":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(run_full_analysis.subprocess, "run", fake_run)

    try:
        run_full_analysis.run_pipeline()
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("pipeline failure was not propagated")

    assert calls == list(run_full_analysis.PIPELINE_MODULES[:4])
