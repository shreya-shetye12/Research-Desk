"""Offline fixtures verify gates. Simulated learning here is not product evidence."""

import copy
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend import corpus, engine, evaluation, jobs, learning, model, store
from backend.api import app, TOKEN
from backend.calculator import calculate
from backend.models import Selection


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIFT_TRACKING", "0")
    monkeypatch.setenv("SHIFT_SEMANTIC", "0")
    monkeypatch.setattr(store, "DB", tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(
        model,
        "health",
        lambda: {
            "ready": True,
            "connected": True,
            "name": "fixture",
            "digest": "fixture-digest",
        },
    )
    store.initialize()


@pytest.fixture
def case():
    return corpus.brief("target23_margin")


def result(c, correct=True):
    ref = evaluation.references(c["split"])[c["id"]]
    return {
        "status": "answer",
        "operand_ids": ref["operand_ids"] if correct else ["wrong", "wrong"],
        "result": ref["result"] if correct else -99,
        "qualification": "Reported figures; fiscal weeks differ.",
        "seconds": 1,
        "explanation": "Explicit isolated fixture",
        "formula": "fixture",
        "sources": c["cells"][:2],
        "memory": [],
    }


def candidate(case, parent_id=None):
    aid = store.put(
        "attempt",
        {
            "case": case,
            "mode": "baseline",
            "result": result(case, False),
            "review": "unreviewed",
        },
    )
    draft = {
        "procedure": "Check the requested revenue basis against report definitions before selecting source operands.",
        "conditions": ["The requested revenue basis is explicit."],
        "exclusions": "Do not transfer company-specific revenue mappings across companies or conventions.",
        "rationale": "Source definitions determine comparability.",
    }
    with patch.object(model, "chat", return_value=draft):
        return learning.propose(
            aid,
            "Source-checked fixture correction: use the requested total revenue basis.",
            True,
            parent_id,
        )["procedure_id"]


def positive_replay(c, mode, procedures, history=None):
    matches = (
        c["company"] == "Target"
        and c["report"] == "target_separate_sales_total_revenue"
        and c["task"] == "operating_margin"
    )
    return result(c, correct=bool(procedures) or not matches)


def test_every_authored_reference_matches_restricted_arithmetic():
    for c in corpus.cases():
        ref = evaluation.references(c["split"])[c["id"]]
        actual = calculate(c, {"status": "answer", "operand_ids": ref["operand_ids"]})
        assert actual["result"] == pytest.approx(ref["result"])


@pytest.mark.parametrize(
    "violation", ["unknown", "duplicate", "unit", "period", "nonfinite", "zero"]
)
def test_bad_operands_fail(case, violation):
    c = copy.deepcopy(case)
    ids = evaluation.references("learning")[c["id"]]["operand_ids"].copy()
    first = next(v for v in c["cells"] if v["id"] == ids[0])
    second = next(v for v in c["cells"] if v["id"] == ids[1])
    if violation == "unknown":
        ids[0] = "invented"
    if violation == "duplicate":
        ids[0] = ids[1]
    if violation == "unit":
        first["unit"] = "USD billions"
    if violation == "period":
        first["period"] = 2000
    if violation == "nonfinite":
        first["value"] = float("nan")
    if violation == "zero":
        second["value"] = 0
    with pytest.raises(ValueError):
        calculate(c, {"status": "answer", "operand_ids": ids})


def test_grouped_splits_and_reference_isolation():
    assert corpus.integrity()["passed"]
    assert corpus.integrity()["counts"] == {
        "learning": 16,
        "validation": 12,
        "final": 5,
    }
    with pytest.raises(ValueError):
        corpus.brief(corpus.cases("final")[0]["id"])
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert all(c["split"] == "learning" for c in state["cases"])
        for path in [
            "/data/final_gold.json",
            "/data/cases.json",
            "/../data/final_gold.json",
            "/backend/evaluation.py",
        ]:
            assert client.get(path).status_code == 404


def test_request_token_origin_and_schema_gates():
    with TestClient(app) as client:
        assert (
            client.post("/api/analyze", json={"case_id": "target23_margin"}).status_code
            == 403
        )
        headers = {"x-workspace-token": TOKEN, "origin": "https://elsewhere.example"}
        assert (
            client.post(
                "/api/analyze", headers=headers, json={"case_id": "target23_margin"}
            ).status_code
            == 403
        )
        headers.pop("origin")
        assert (
            client.post(
                "/api/analyze", headers=headers, json={"case_id": "target20_margin"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/analyze",
                headers=headers,
                json={"case_id": "target23_margin", "mode": "pretend"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/freeze", headers=headers, json={"reviewed": False}
            ).status_code
            == 400
        )


def test_candidates_are_inactive_and_unchecked_teaching_is_rejected(case):
    aid = store.put("attempt", {"case": case, "result": result(case)})
    with pytest.raises(ValueError):
        learning.propose(aid, "Unverified fixture correction", False)
    pid = candidate(case)
    assert engine.memory(case, "lessons") == []
    with pytest.raises(ValueError):
        learning.decide(pid, "accepted", True)


def test_latest_checked_feedback_per_attempt_is_reused_without_erasing_history(case):
    for aid, text in [
        ("one", "Earlier correction"),
        ("two", "Other attempt"),
        ("one", "Revised correction"),
    ]:
        store.put("correction", {"attempt_id": aid, "text": text, "checked": True})
    used = engine.memory(case, "history")
    assert used == [{"text": "Revised correction"}, {"text": "Other attempt"}]
    assert len(store.rows("correction")) == 3
    assert engine.memory(case, "baseline") == []
    assert engine.memory(case, "lessons") == []


def test_feedback_history_limit_applies_after_revision_deduplication():
    items = [{"attempt_id": "one", "text": str(i)} for i in range(12)]
    items += [{"attempt_id": str(i), "text": "distinct"} for i in range(2, 12)]
    history = engine.correction_history(items)
    assert len(history) == 8
    assert history[0]["text"] == "0"
    assert len({i["attempt_id"] for i in history}) == 8
    assert len(items) == 22


def test_feedback_history_preserves_unidentified_legacy_entries():
    items = [{"text": "one"}, {"text": "two"}]
    assert engine.correction_history(items) == items


def test_teacher_repairs_a_concrete_draft_before_saving(case):
    aid = store.put("attempt", {"case": case, "result": result(case)})
    bad = {
        "procedure": "Calculate the FY2024 margin using the requested revenue.",
        "conditions": ["Use FY2024."],
        "exclusions": "Do not use other years.",
        "rationale": "Fixture, not observed learning.",
    }
    good = {
        **bad,
        "procedure": "Copy the income cell ID first and the requested revenue cell ID second from the labeled source rows.",
        "conditions": ["Use the requested period."],
        "exclusions": "Do not infer source IDs from row positions.",
        "binding": {
            "kind": "source_label_binding",
            "first_label": "Operating income",
            "second_label": "Total revenue",
            "period_kind": "annual",
            "revenue_basis": "total_revenue",
        },
    }
    with patch.object(model, "chat", side_effect=[bad, good]) as teacher:
        pid = learning.propose(
            aid, "Check actual source row labels before copying ordered IDs.", True
        )["procedure_id"]
    assert teacher.call_count == 2
    assert store.get("procedure", pid)["procedure"] == good["procedure"]
    assert store.get("procedure", pid)["status"] == "candidate"


def test_teacher_does_not_save_feedback_if_repair_still_memorizes(case):
    aid = store.put("attempt", {"case": case, "result": result(case)})
    draft = {
        "procedure": "Calculate operating margin for FY2024 only.",
        "conditions": ["Use FY2024."],
        "exclusions": "Do not use other years.",
        "rationale": "Fixture, not observed learning.",
    }
    with patch.object(model, "chat", return_value=draft) as teacher:
        with pytest.raises(ValueError, match="not reusable"):
            learning.propose(
                aid, "Check actual source row labels before copying ordered IDs.", True
            )
    assert teacher.call_count == 2
    assert store.rows("correction") == []
    assert store.rows("procedure") == []


def test_percentage_conversion_is_not_confused_with_a_memorized_answer():
    draft = {
        "procedure": "Divide operating income by requested revenue and multiply by 100.",
        "conditions": ["Match the requested period."],
        "exclusions": "Exclude unrelated periods.",
    }
    assert not learning.memorized(draft)
    assert learning.memorized(
        {**draft, "procedure": "The operating margin is 100 percent."}
    )
    assert learning.memorized({**draft, "procedure": "For FY2024, multiply by 100."})


def test_replay_and_freeze_use_the_same_latest_feedback_policy():
    for text in ["Earlier correction", "Revised correction"]:
        store.put("correction", {"attempt_id": "same", "text": text, "checked": True})
    frozen = store.get("freeze", evaluation.freeze(True)["freeze_id"])
    assert [c["text"] for c in frozen["history"]] == ["Revised correction"]
    with patch.object(
        engine, "analyze", side_effect=lambda c, *args: result(c)
    ) as analyze:
        evaluation.replay("validation")
    for call in analyze.call_args_list:
        assert [c["text"] for c in call.args[3]] == ["Revised correction"]


def test_validation_with_no_gain_cannot_be_approved(case):
    pid = candidate(case)
    with patch.object(engine, "analyze", side_effect=lambda c, *args, **kw: result(c)):
        learning.validate(pid)
    assert not store.get("procedure", pid)["validation"]["eligible"]
    with pytest.raises(ValueError):
        learning.decide(pid, "accepted", True)


def test_refinement_reuses_checked_correction_and_preserves_old_candidate(case):
    pid = candidate(case)
    original = store.get("procedure", pid)
    draft = {
        k: original[k] for k in ["procedure", "conditions", "exclusions", "rationale"]
    }
    with patch.object(model, "chat", return_value=draft):
        refined = learning.refine(pid)["procedure_id"]
    new = store.get("procedure", refined)
    assert refined != pid
    assert new["refines_candidate_id"] == pid
    assert new["correction_id"] == original["correction_id"]
    assert new["status"] == "candidate" and new["validation"] is None
    assert store.get("procedure", pid) == original
    assert len(store.rows("correction")) == 1


def test_refinement_rejects_unchecked_feedback_and_accepted_procedures(case):
    pid = candidate(case)
    p = store.get("procedure", pid)
    store.update("correction", p["correction_id"], checked=False)
    with pytest.raises(ValueError, match="source-checked"):
        learning.refine(pid)
    store.update("procedure", pid, status="accepted")
    with pytest.raises(ValueError, match="inactive"):
        learning.refine(pid)


def test_positive_fixture_requires_review_and_preserves_scope(case):
    pid = candidate(case)
    with patch.object(engine, "analyze", side_effect=positive_replay):
        learning.validate(pid)
    gate = store.get("procedure", pid)["validation"]
    assert gate["eligible"] and gate["gains"] > 0 and gate["regressions"] == 0
    with pytest.raises(ValueError):
        learning.decide(pid, "accepted", False)
    learning.decide(pid, "accepted", True)
    assert len(engine.memory(case, "lessons")) == 1
    assert engine.memory(corpus.brief("target24_growth"), "lessons") == []
    assert engine.memory(corpus.brief("costco24_growth"), "lessons") == []
    learning.decide(pid, "disabled")
    assert engine.memory(case, "lessons") == []


def test_any_observed_regression_blocks_acceptance(case):
    pid = candidate(case)

    def replay(c, mode, procedures):
        match = c["report"] == case["report"] and c["task"] == case["task"]
        return result(c, correct=bool(procedures) if match else not procedures)

    with patch.object(engine, "analyze", side_effect=replay):
        learning.validate(pid)
    gate = store.get("procedure", pid)["validation"]
    assert gate["gains"] > 0 and gate["regressions"] > 0 and not gate["eligible"]


def test_changed_model_or_active_memory_invalidates_approval(case):
    pid = candidate(case)
    with patch.object(engine, "analyze", side_effect=positive_replay):
        learning.validate(pid)
    with patch.object(model, "health", return_value={"digest": "changed"}):
        with pytest.raises(ValueError, match="stale"):
            learning.decide(pid, "accepted", True)
    other = candidate(case)
    store.update("procedure", other, status="accepted")
    with pytest.raises(ValueError, match="stale"):
        learning.decide(pid, "accepted", True)


def test_changed_candidate_invalidates_approval(case):
    pid = candidate(case)
    with patch.object(engine, "analyze", side_effect=positive_replay):
        learning.validate(pid)
    store.update(
        "procedure",
        pid,
        procedure="Changed fixture procedure after validation; not acceptable without another replay.",
    )
    with pytest.raises(ValueError, match="stale"):
        learning.decide(pid, "accepted", True)


def test_revision_supersedes_parent_only_after_approval(case):
    pid = candidate(case)
    with patch.object(engine, "analyze", side_effect=positive_replay):
        learning.validate(pid)
    learning.decide(pid, "accepted", True)
    revision = candidate(case, pid)
    assert store.get("procedure", revision)["version"] == 2
    assert store.get("procedure", pid)["status"] == "accepted"

    def replay(c, mode, procedures):
        trial = any(p["id"] == revision for p in procedures)
        match = c["report"] == case["report"] and c["task"] == case["task"]
        return result(c, correct=trial or not match)

    with patch.object(engine, "analyze", side_effect=replay):
        learning.validate(revision)
    learning.decide(revision, "accepted", True)
    assert store.get("procedure", pid)["status"] == "superseded"
    assert len(learning.active()) == 1


def test_final_needs_freeze_and_exposure_is_not_repeatable():
    with pytest.raises(ValueError):
        evaluation.freeze(False)
    with pytest.raises(ValueError):
        evaluation.replay("final")
    frozen = evaluation.freeze(True)["freeze_id"]
    with patch.object(engine, "analyze", side_effect=lambda c, *args, **kw: result(c)):
        eid = evaluation.replay("final", frozen)["evaluation_id"]
        assert store.get("evaluation", eid)["first_final_exposure"]
        with pytest.raises(ValueError, match="already exposed"):
            evaluation.replay("final", frozen)
        next_freeze = evaluation.freeze(True)["freeze_id"]
        repeated = evaluation.replay("final", next_freeze)["evaluation_id"]
        assert not store.get("evaluation", repeated)["first_final_exposure"]


def test_interrupted_final_still_counts_as_exposure():
    frozen = evaluation.freeze(True)["freeze_id"]
    with patch.object(
        engine, "analyze", side_effect=OSError("Isolated failure fixture")
    ):
        with pytest.raises(OSError):
            evaluation.replay("final", frozen)
    assert store.rows("evaluation")[0]["status"] == "interrupted"
    with pytest.raises(ValueError, match="already exposed"):
        evaluation.replay("final", frozen)


def test_model_change_rejects_frozen_final():
    frozen = evaluation.freeze(True)["freeze_id"]
    with patch.object(model, "health", return_value={"digest": "changed"}):
        with pytest.raises(ValueError, match="changed"):
            evaluation.replay("final", frozen)


def test_review_and_memo_preserve_original_evidence(case):
    aid = store.put(
        "attempt",
        {
            "case": case,
            "mode": "baseline",
            "result": result(case),
            "review": "unreviewed",
        },
    )
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/reviews",
                headers={"x-workspace-token": TOKEN},
                json={"id": aid, "status": "reviewed"},
            ).status_code
            == 200
        )
        a = client.get("/api/state").json()["attempts"][0]
        assert a["review"] == "reviewed"
        memo = client.get("/api/memo/" + aid)
        assert case["cells"][0]["source"] in memo.text and case["notes"] in memo.text
        assert "Human review: reviewed" in memo.text


def test_report_change_is_a_signal_with_original_notes():
    change = corpus.changes()[0]
    assert (
        change["company"] == "Target"
        and "Sales" in change["removed"]
        and "Net Sales" in change["added"]
    )
    assert change["old_notes"] and change["new_notes"]


def test_only_one_local_worker_and_restart_records_interruption():
    jobs.BUSY.acquire()
    try:
        with pytest.raises(ValueError, match="already running"):
            jobs.submit("Fixture", lambda emit: None)
    finally:
        jobs.BUSY.release()
    store.put("job", {"status": "running", "message": "Fixture"})
    jobs.recover()
    assert store.rows("job")[0]["status"] == "interrupted"


def test_model_outputs_reject_extra_fields():
    with pytest.raises(ValueError):
        Selection(
            status="answer",
            operand_ids=[],
            explanation="Fixture",
            qualification="",
            invented_answer=123,
        )
