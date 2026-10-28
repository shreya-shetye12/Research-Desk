"""Learned lookup actions are bounded, scoped and independent of row-ID order.

These are software fixtures, not empirical learning results.
"""

import copy
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from backend import bindings, corpus, engine, learning, model, store
from backend.models import LabelBinding


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIFT_TRACKING", "0")
    monkeypatch.setattr(store, "DB", tmp_path / "ledger.sqlite3")
    store.initialize()


@pytest.fixture
def case():
    return copy.deepcopy(
        next(
            c
            for c in corpus.cases("validation")
            if c["id"] == "costco16_imported_annual_margin"
        )
    )


@pytest.fixture
def binding():
    return {
        "kind": "source_label_binding",
        "first_label": "Operating income",
        "second_label": "Total revenue",
        "period_kind": "annual",
        "revenue_basis": "total_revenue",
    }


def lesson(case, binding, status="accepted"):
    return {
        "id": "fixture_procedure",
        "version": 1,
        "status": status,
        **{k: case[k] for k in ["company", "task", "report"]},
        "procedure": "Read each actual source label before copying ordered source IDs.",
        "conditions": ["Use annual figures on the total-revenue basis."],
        "exclusions": "Exclude quarterly and net-sales tasks.",
        "binding": binding,
    }


def selection():
    return {
        "status": "answer",
        "operand_ids": ["guessed_first", "guessed_second"],
        "explanation": "Isolated fixture with wrong IDs",
        "qualification": "",
    }


def test_lookup_uses_labels_and_period_not_id_suffixes_or_row_order(case, binding):
    for index, cell in enumerate(case["cells"]):
        cell["id"] = f"opaque-{100-index}"
    income = case["cells"][0]["id"]
    revenue = case["cells"][1]["id"]
    case["cells"].reverse()
    assert bindings.resolve(binding, case) == [income, revenue]


def test_source_case_and_policy_are_not_mutated(case, binding):
    original = copy.deepcopy((case, binding))
    bindings.resolve(binding, case)
    assert (case, binding) == original


def test_year_and_period_kind_select_annual_prior_year_not_current_quarter(
    case, binding
):
    case["period"] = 2015
    case["question"] = (
        "Calculate full-year FY2015 operating margin using total revenue."
    )
    assert bindings.resolve(binding, case) == [
        case["cells"][4]["id"],
        case["cells"][5]["id"],
    ]


@pytest.mark.parametrize(
    "variation",
    ["missing", "duplicate", "wrong_company", "wrong_units", "ambiguous_location"],
)
def test_uncertain_source_binding_requires_review(case, binding, variation):
    if variation == "missing":
        case["cells"][0]["label"] = "Unrecognized operating result"
    if variation == "duplicate":
        case["cells"].append({**case["cells"][0], "id": "duplicate"})
    if variation == "wrong_company":
        case["cells"][0]["company"] = "Target"
    if variation == "wrong_units":
        case["cells"][0]["unit"] = "USD billions"
    if variation == "ambiguous_location":
        case["cells"][0]["location"] = "Annual and quarterly amounts"
    final = bindings.apply(case, selection(), [lesson(case, binding)])
    assert final["status"] == "review"
    assert final["operand_ids"] == []
    assert final["procedure_execution"]["status"] == "review"


def test_scope_excludes_basis_quarter_company_convention_and_task(case, binding):
    p = lesson(case, binding)
    for changes in [
        {"revenue_basis": "sales"},
        {
            "question": "Calculate fourth-quarter FY2016 operating margin using total revenue."
        },
        {"company": "Target"},
        {"report": "different_convention"},
        {"task": "revenue_growth"},
    ]:
        assert not engine.applicable(p, {**case, **changes})
    assert engine.applicable(p, case)


def test_ambiguous_request_does_not_activate_a_binding(case, binding):
    case["question"] = "Calculate annual and fourth-quarter operating margins."
    assert bindings.requested_kind(case) is None
    assert not engine.applicable(lesson(case, binding), case)


def test_only_accepted_applicable_procedures_execute(case, binding):
    p = lesson(case, binding)
    wrong = selection()
    with patch.object(model, "chat", return_value=wrong):
        for mode in ["baseline", "history"]:
            actual, used = engine.select(case, mode, [p], [])
            assert actual == wrong and used == []
        actual, used = engine.select(case, "lessons", [dict(p, status="candidate")])
        assert actual == wrong and used == []
        actual, used = engine.select(case, "lessons", [p])
    assert actual["operand_ids"] == [case["cells"][0]["id"], case["cells"][1]["id"]]
    assert actual["procedure_execution"]["original_selection"] == wrong
    assert actual["procedure_execution"]["actions"][0]["procedure_id"] == p["id"]
    assert used[0]["binding"] == binding


def test_conflicting_bindings_require_review(case, binding):
    first = lesson(case, binding)
    second = lesson(case, {**binding, "second_label": "Net sales"})
    second["id"] = "conflicting_procedure"
    actual = bindings.apply(case, selection(), [first, second])
    assert actual["status"] == "review"
    assert "disagree" in actual["qualification"]


def test_action_schema_cannot_contain_arbitrary_code_or_numeric_answers(binding):
    with pytest.raises(ValidationError):
        LabelBinding.model_validate({**binding, "code": "arbitrary code"})
    with pytest.raises(ValidationError):
        LabelBinding.model_validate({**binding, "answer": 3.09})


def test_source_id_is_not_accepted_as_a_source_label(case, binding):
    with pytest.raises(ValueError, match="matching source rows"):
        bindings.resolve({**binding, "first_label": case["cells"][0]["id"]}, case)


def test_binding_changes_invalidate_candidate_hash(case, binding):
    p = lesson(case, binding)
    assert learning.content_hash(p) != learning.content_hash(
        {**p, "binding": {**binding, "second_label": "Net sales"}}
    )


def test_malformed_stored_action_does_not_enter_memory(case, binding):
    assert not engine.applicable(lesson(case, {**binding, "code": "unsupported"}), case)


def test_auditor_checks_current_binding_while_original_selection_is_retained(
    case, binding
):
    wrong = selection()
    bound = bindings.apply(case, wrong, [lesson(case, binding)])
    with patch.object(model, "chat", return_value={"supported": True}) as auditor:
        engine.audit(case, bound)
    payload = auditor.call_args.args[1]
    assert payload["selection"]["operand_ids"] == bound["operand_ids"]
    assert "procedure_execution" not in payload["selection"]
    assert payload["selection"]["source_bindings"][0]["binding"] == binding
    assert bound["procedure_execution"]["original_selection"] == wrong


def test_teacher_requires_a_binding_for_a_source_identifier_correction(case):
    draft = {
        "procedure": "Copy source row IDs carefully in the requested order.",
        "conditions": ["Match the requested period."],
        "exclusions": "Do not infer IDs from row numbers.",
        "rationale": "Avoid source identifier confusion.",
    }
    assert any(
        "needs a source_label_binding" in issue
        for issue in learning.draft_issues(
            draft, case, "Correct the source IDs and operand order."
        )
    )


def test_teacher_binding_must_match_the_checked_source_and_basis(case, binding):
    draft = {
        "procedure": "Copy source row IDs carefully in the requested order.",
        "conditions": ["Match the requested period."],
        "exclusions": "Do not infer IDs from row numbers.",
        "rationale": "Avoid source identifier confusion.",
        "binding": {**binding, "second_label": "Invented revenue"},
    }
    assert learning.draft_issues(draft, case, "Correct the source IDs.")
    draft["binding"] = {**binding, "revenue_basis": "sales"}
    assert learning.draft_issues(draft, case, "Correct the source IDs.")
