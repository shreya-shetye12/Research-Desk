"""Restored capabilities tested with isolated state and explicit model fixtures."""

import base64
import copy
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from backend import (
    corpus,
    engine,
    ingestion,
    model,
    observability,
    retrieval,
    store,
    workflow,
    evaluation,
    jobs,
)
from backend.models import Import, Curate


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIFT_TRACKING", "0")
    monkeypatch.setenv("SHIFT_SEMANTIC", "0")
    monkeypatch.setattr(store, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(model, "health", lambda: {"digest": "fixture-digest"})
    store.initialize()


def test_hybrid_search_uses_local_vectors_and_an_exact_eligible_allowlist(monkeypatch):
    class Collection:
        def get(self, ids):
            return {"ids": []}

        def upsert(self, **kwargs):
            self.ids = kwargs["ids"]

        def query(self, **kwargs):
            assert set(kwargs["where"]["evidence_id"]["$in"]) == set(self.ids)
            return {"ids": [list(reversed(self.ids))]}

    collection = Collection()
    monkeypatch.setattr(
        retrieval,
        "client",
        lambda: SimpleNamespace(
            get_or_create_collection=lambda *args, **kwargs: collection
        ),
    )
    calls = []

    def embed(texts):
        calls.extend(texts)
        return [[1.0, 0.0] for t in texts]

    monkeypatch.setattr(model, "embed", embed)
    packs = corpus.packs()
    ranked, details = retrieval.retrieve(
        "Target revenue definition FY2024", packs, True
    )
    assert details["strategy"] == "hybrid_rrf" and len(ranked) == len(packs)
    assert all(p["split"] == "learning" for p in ranked)
    assert any(t.startswith("search_document: ") for t in calls)
    assert any(t.startswith("search_query: ") for t in calls)


def test_semantic_failure_is_recorded_as_keyword_fallback(monkeypatch):
    monkeypatch.setattr(
        retrieval,
        "client",
        lambda: (_ for _ in ()).throw(OSError("Isolated vector failure")),
    )
    ranked, details = retrieval.retrieve("Revenue", corpus.packs(), True)
    assert ranked and details["strategy"] == "bm25" and details["qualification"]


def fixture_pdf():
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    text = b"BT /F1 12 Tf 72 720 Td (Fixture report: revenue 1000000, operating income 50000.) Tj ET"
    objects.append(
        b"<< /Length "
        + str(len(text)).encode()
        + b" >>\nstream\n"
        + text
        + b"\nendstream"
    )
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    )
    return pdf


def test_pdf_extraction_stays_inactive_until_checked_curation():
    doc = ingestion.ingest(
        Import(
            name="Isolated PDF fixture",
            company="Target",
            source_url="https://example.com/report",
            format="pdf",
            content=base64.b64encode(fixture_pdf()).decode(),
        )
    )
    d = store.get("document", doc["document_id"])
    assert "revenue 1000000" in d["content"] and d["status"] == "needs_curation"
    assert not any(p.get("document_id") == d["id"] for p in corpus.packs())
    cells = [
        dict(
            id="fixture_" + str(i),
            company="Target",
            period=2025,
            label=label,
            value=value,
            unit="USD millions",
            source=d["source"],
            location="Fixture page 1",
        )
        for i, (label, value) in enumerate(
            [("Revenue", 1000000), ("Operating income", 50000)]
        )
    ]
    request = dict(
        document_id=d["id"],
        company="Target",
        convention="new_convention",
        notes="Fixture evidence only: reported revenue and income.",
        cells=cells,
        checked=False,
    )
    with pytest.raises(ValueError):
        ingestion.curate(Curate(**request))
    request["checked"] = True
    result = ingestion.curate(Curate(**request))
    p = store.get("pack", result["pack_id"])
    assert (
        p["report"] == "new_convention:" + d["id"]
        and p["source_review"] == "human attested"
    )
    assert store.get("document", d["id"])["status"] == "curated"


def test_import_cannot_shadow_reserved_reference_figures():
    cell = copy.deepcopy(corpus.cases("final")[0]["cells"][0])
    doc = ingestion.ingest(
        Import(
            name="Reserved fixture",
            company=cell["company"],
            source_url=cell["source"],
            format="text",
            content=f"Isolated reserved figure fixture: {cell['value']} USD millions.",
        )
    )
    second = dict(cell, id="another-fixture")
    with pytest.raises(ValueError, match="reserved"):
        ingestion.curate(
            Curate(
                document_id=doc["document_id"],
                company=cell["company"],
                convention="new_convention",
                notes="Reserved evidence must not enter teaching.",
                cells=[cell, second],
                checked=True,
            )
        )


def test_html_scripts_removed_and_invented_figures_rejected():
    doc = ingestion.ingest(
        Import(
            name="HTML fixture",
            company="Target",
            source_url="https://example.com/report",
            format="html",
            content="<script>untrusted instruction</script><p>Fixture report revenue 1000; income 100; fiscal period 2025.</p>",
        )
    )
    d = store.get("document", doc["document_id"])
    assert "untrusted instruction" not in d["content"]
    cells = [
        dict(
            id=str(i),
            company="Target",
            period=2025,
            label=label,
            value=value,
            unit="USD millions",
            source=d["source"],
            location="Fixture paragraph",
        )
        for i, (label, value) in enumerate([("Revenue", 10), ("Income", 100)])
    ]
    with pytest.raises(ValueError, match="not found"):
        ingestion.curate(
            Curate(
                document_id=d["id"],
                company="Target",
                convention="new_convention",
                notes="Isolated fixture for invented operand rejection.",
                cells=cells,
                checked=True,
            )
        )


def make_job():
    return store.put(
        "job", {"events": [], "status": "running", "kind": "analysis", "result": None}
    )


def test_graph_pauses_at_human_review_and_resumes_without_duplicate_artifacts(
    monkeypatch,
):
    graph = workflow.build_graph(InMemorySaver())
    monkeypatch.setattr(workflow, "graph", lambda: graph)
    case = corpus.brief("target23_margin")
    jid = make_job()
    selected = {
        "status": "answer",
        "operand_ids": ["target_2023_oi", "target_2023_revenue"],
        "explanation": "Isolated fixture selection",
        "qualification": "Reported fiscal weeks noted.",
    }
    with patch.object(
        engine, "retrieve_case", return_value={"strategy": "fixture"}
    ), patch.object(engine, "select", return_value=(selected, [])), patch.object(
        engine,
        "audit",
        return_value={"supported": True, "issues": [], "explanation": "Fixture"},
    ):
        result = workflow.execute(
            jid,
            {
                "case": case,
                "question": case["question"],
                "companies": ["Target"],
                "mode": "baseline",
            },
        )
        assert result["status"] == "waiting_review" and len(store.rows("attempt")) == 1
        assert store.rows("review") == []
        completed = workflow.execute(jid, resume={result["attempt_id"]: "reviewed"})
    assert completed["status"] == "complete" and len(store.rows("attempt")) == 1
    assert store.rows("review")[0]["status"] == "reviewed"


def test_checkpoint_retries_only_the_failed_stage(monkeypatch):
    graph = workflow.build_graph(InMemorySaver())
    monkeypatch.setattr(workflow, "graph", lambda: graph)
    case = corpus.brief("target23_margin")
    jid = make_job()
    selected = {
        "status": "answer",
        "operand_ids": ["target_2023_oi", "target_2023_revenue"],
        "explanation": "Isolated fixture",
        "qualification": "",
    }
    with patch.object(
        engine, "retrieve_case", return_value={"strategy": "fixture"}
    ), patch.object(
        engine, "select", return_value=(selected, [])
    ) as select, patch.object(
        engine,
        "audit",
        side_effect=[
            RuntimeError("Isolated transient failure"),
            {"supported": True, "issues": [], "explanation": "Fixture"},
        ],
    ):
        with pytest.raises(RuntimeError):
            workflow.execute(
                jid,
                {
                    "case": case,
                    "question": case["question"],
                    "companies": ["Target"],
                    "mode": "baseline",
                },
            )
        result = workflow.execute(jid)
    assert (
        result["status"] == "waiting_review"
        and select.call_count == 1
        and len(store.rows("attempt")) == 1
    )


def test_mlflow_recording_receives_real_metric_values(monkeypatch):
    from contextlib import contextmanager

    observed = {}

    @contextmanager
    def run(**kwargs):
        yield SimpleNamespace(info=SimpleNamespace(run_id="isolated-run"))

    fake = SimpleNamespace(
        start_run=run,
        log_params=lambda p: observed.update(params=p),
        log_metrics=lambda m: observed.update(metrics=m),
    )
    monkeypatch.setattr(observability, "setup", lambda: fake)
    rid = observability.record_evaluation(
        "fixture",
        {"gains": 2, "regressions": 0, "comment": "not numeric"},
        {"split": "validation"},
    )
    assert rid == "isolated-run" and observed["metrics"] == {
        "gains": 2.0,
        "regressions": 0.0,
    }


def test_imported_catalog_changes_invalidate_experiment_environment():
    before = evaluation.environment()
    store.put(
        "pack",
        {
            **corpus.packs()[0],
            "group": "isolated-changed-source",
            "notes": "Isolated edited definition",
        },
    )
    assert evaluation.environment() != before


def test_every_assignment_result_requires_review_before_graph_resume():
    jid = store.put(
        "job",
        {"events": [], "status": "waiting_review", "kind": "analysis", "result": None},
    )
    aids = [
        store.put(
            "attempt", {"case": corpus.brief("target23_margin"), "workflow_id": jid}
        )
        for _ in range(2)
    ]
    store.update("job", jid, result={"results": [{"id": aid} for aid in aids]})
    with patch.object(jobs.POOL, "submit") as submit, patch.object(
        workflow, "execute", return_value={"status": "complete"}
    ) as execute:
        jobs.review_attempt(aids[0], "reviewed")
        assert not jobs.BUSY.locked() and not submit.called
        jobs.review_attempt(aids[1], "needs_correction")
        assert submit.call_count == 1 and jobs.BUSY.locked()
        callback = submit.call_args.args[2]
        jobs.work(jid, callback)
        execute.assert_called_once_with(
            jid, resume={aids[0]: "reviewed", aids[1]: "needs_correction"}
        )
    assert not jobs.BUSY.locked() and store.get("job", jid)["status"] == "complete"


@pytest.mark.parametrize("change", ["company", "task", "year", "prior", "duplicates"])
def test_single_margin_plan_rejects_out_of_scope_or_repeated_steps(change):
    plan = {
        "summary": "Fixture",
        "clarification": "",
        "steps": [
            dict(
                company="Costco",
                task="operating_margin",
                period=2024,
                prior_period=2024,
                revenue_basis="total_revenue",
            )
        ],
    }
    question = "Calculate Costco FY2024 full-year operating margin using total revenue."
    schema = workflow.plan_schema(["Costco"], question)
    assert schema.model_validate(plan)
    if change == "company":
        plan["steps"][0]["company"] = "Cost,co"
    if change == "task":
        plan["steps"][0]["task"] = "revenue_growth"
    if change == "year":
        plan["steps"][0]["period"] = 2023
    if change == "prior":
        plan["steps"][0]["prior_period"] = 2023
    if change == "duplicates":
        plan["steps"] *= 6
    assert workflow.plan_issues(plan, ["Costco"], question)
    with pytest.raises(ValueError):
        schema.model_validate(plan)


def test_pinned_source_survives_planner_repair_and_retrieval(monkeypatch):
    graph = workflow.build_graph(InMemorySaver())
    monkeypatch.setattr(workflow, "graph", lambda: graph)
    original = next(p for p in corpus.packs() if p["company"] == "Costco")
    pinned = {
        **copy.deepcopy(original),
        "id": "fixture-upload",
        "report": "new_convention:fixture",
        "name": "Uploaded fixture",
        "source_review": "human attested",
    }
    monkeypatch.setattr(corpus, "packs", lambda: [original, pinned])
    step = dict(
        company="Costco",
        task="operating_margin",
        period=2024,
        prior_period=2024,
        revenue_basis="total_revenue",
    )
    bad = {
        "summary": "Fixture invalid",
        "clarification": "",
        "steps": [{**step, "company": "Cost,co"}],
    }
    good = {"summary": "Fixture scoped", "clarification": "", "steps": [step]}
    calls = []

    def planner(system, payload, schema):
        assert [p["id"] for p in payload["available_reports"]] == ["fixture-upload"]
        calls.append(payload)
        return bad if len(calls) == 1 else good

    monkeypatch.setattr(model, "chat", planner)

    def retrieve(query, docs, semantic):
        assert [p["id"] for p in docs] == ["fixture-upload"]
        return docs, {"strategy": "fixture", "ranked_reports": ["fixture-upload"]}

    monkeypatch.setattr(workflow, "retrieve", retrieve)
    selection = dict(
        status="answer",
        operand_ids=["costco_2024_oi", "costco_2024_revenue"],
        explanation="Fixture selection",
        qualification="",
    )
    monkeypatch.setattr(engine, "select", lambda *args: (selection, []))
    monkeypatch.setattr(
        engine,
        "audit",
        lambda *args: {"supported": True, "issues": [], "explanation": "Fixture"},
    )
    question = "Using my uploaded report, calculate Costco FY2024 full-year operating margin using total revenue."
    result = workflow.execute(
        make_job(),
        {
            "question": question,
            "companies": ["Costco"],
            "source_id": "fixture-upload",
            "mode": "baseline",
        },
    )
    case = result["results"][0]["case"]
    assert len(calls) == 2 and "repair_required" in calls[1]
    assert result["status"] == "waiting_review" and len(result["results"]) == 1
    assert (
        case["source_pack_id"] == "fixture-upload"
        and case["source_name"] == "Uploaded fixture"
    )
    assert (
        case["report"] == "new_convention:fixture"
        and case["request_context"] == question
    )


def test_pinned_source_api_rejects_wrong_company_or_unknown_source(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import api

    source = next(p for p in corpus.packs() if p["company"] == "Costco")
    captured = []
    monkeypatch.setattr(
        jobs,
        "analysis",
        lambda payload: captured.append(payload) or {"job_id": "fixture"},
    )
    headers = {"x-workspace-token": api.TOKEN}
    body = {
        "question": "Calculate Costco FY2024 operating margin using total revenue.",
        "companies": ["Costco"],
        "source_id": source["id"],
        "mode": "baseline",
    }
    with TestClient(api.app) as client:
        assert (
            client.post(
                "/api/assignments",
                json={**body, "companies": ["Target"]},
                headers=headers,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/assignments",
                json={**body, "source_id": "reserved-or-unknown"},
                headers=headers,
            ).status_code
            == 400
        )
        assert not captured
        assert (
            client.post("/api/assignments", json=body, headers=headers).status_code
            == 202
        )
    assert captured[0]["source_id"] == source["id"]
