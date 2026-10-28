"""Offline evaluation checks; not empirical model results."""
import copy
import json
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend import benchmark, bindings, corpus, engine, evaluation, model, store
from backend.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_original_branding_and_app_files_are_preserved():
    original = json.loads((ROOT / "SOURCE_PROVENANCE.json").read_text())["original_files"]
    changed_for_evaluation = {"README.md", "data/cases.json", "data/validation_gold.json", "tests/test_workflow.py"}
    for name, digest in original.items():
        if name not in changed_for_evaluation:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIFT_TRACKING", "0")
    monkeypatch.setattr(store, "DB", tmp_path / "workspace.sqlite3")
    monkeypatch.setattr(model, "health", lambda: {"ready": True, "connected": True, "digest": "offline-fixture", "name": "fixture"})
    store.initialize()


def test_counts_ids_and_source_isolation():
    assert corpus.integrity()["counts"] == {"learning": 16, "validation": 50, "final": 5}
    assert corpus.integrity()["passed"]
    assert len({c["id"] for c in corpus.cases()}) == 71
    assert len({c["group"] for c in corpus.cases("validation")}) == 3


def test_original_twelve_and_answers_are_preserved():
    current = {c["id"]: c for c in corpus.cases("validation")}
    for case in benchmark.load("validation_original.json"):
        assert current[case["id"]] == case
    references = evaluation.references("validation")
    for identifier, original in benchmark.load("validation_original_gold.json").items():
        assert references[identifier] == original


def test_variants_are_explicit_and_preserve_financial_evidence():
    manifest = benchmark.load("validation_manifest.json")
    metadata = manifest["cases"]
    counts = {kind: sum(m["category"] == kind for m in metadata.values()) for kind in ["original", "additional_calculation", "row_order", "opaque_ids"]}
    assert counts == {"original": 12, "additional_calculation": 18, "row_order": 10, "opaque_ids": 10}
    cases, refs = {c["id"]: c for c in corpus.cases("validation")}, evaluation.references("validation")
    def facts(case):
        return sorted(json.dumps({k: v for k, v in cell.items() if k != "id"}, sort_keys=True) for cell in case["cells"])
    for identifier, item in metadata.items():
        assert refs[identifier]["result"] == refs[item["parent"]]["result"]
        assert facts(cases[identifier]) == facts(cases[item["parent"]])
    assert manifest["unique_calculations"] == 30


def test_reference_rule_is_not_a_human_approved_app_procedure():
    fixture = benchmark.load("comparison_rule.json")
    assert fixture["provenance"]["human_approved"] is False
    assert "status" not in fixture["rule"]
    assert fixture["provenance"]["learning_case"] in {c["id"] for c in corpus.cases("learning")}
    assert store.rows("procedure") == []


@pytest.mark.parametrize("identifier,expected", [("costco16_imported_annual_margin", True), ("costco16_imported_quarter_margin", False), ("costco16_imported_sales_margin", False), ("target20_margin", False)])
def test_rule_respects_company_basis_and_period_boundaries(identifier, expected):
    case = next(c for c in corpus.cases("validation") if c["id"] == identifier)
    assert benchmark.in_scope(case, benchmark.load("comparison_rule.json")["rule"]) == expected


def test_model_facing_cases_do_not_contain_reference_answers():
    for case in corpus.cases():
        assert not {"operand_ids", "result", "gold", "correct"}.intersection(case)


def test_numeric_answer_alone_does_not_pass():
    ref = {"operand_ids": ["income", "revenue"], "result": 3.65}
    assert not evaluation.score({"status": "answer", "operand_ids": ["revenue", "income"], "result": 3.65}, ref)["correct"]


def test_runtime_error_counts_as_incorrect(monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError("offline fixture")
    monkeypatch.setattr(engine, "analyze", fail)
    result = benchmark.invoke({"id": "fixture"}, "baseline", {}, {})
    assert result["error"]["type"] == "TimeoutError"
    assert result["score"]["correct"] is False


def test_report_refuses_partial_outputs(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text('{"status":"running","rows":[]}')
    with pytest.raises(ValueError, match="completed"):
        benchmark.report(path)


def test_summary_keeps_gains_regressions_and_errors_separate():
    def row(a, b, category, error=None):
        return {"category": category, "source_group": "report", "applicable": True, "baseline": {"score": {"correct": a, "review_requested": False}}, "reference_rule": {"score": {"correct": b, "review_requested": bool(error)}, "error": error}}
    result = benchmark.summarize([row(False, True, "original"), row(True, False, "additional_calculation"), row(False, False, "opaque_ids", {"type": "TimeoutError"})])
    assert result["overall"]["gains"] == result["overall"]["regressions"] == 1
    assert result["overall"]["reference_rule"]["errors"] == 1
    assert result["distinct_calculations"]["cases"] == 2
