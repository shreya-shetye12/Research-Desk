"""Small paired replay. References stay here, outside model and teaching inputs."""

import json
import math
import re
import os
from . import corpus, engine, model, store
from .store import ROOT


def references(split):
    name = {"learning": "development", "validation": "validation", "final": "final"}[
        split
    ]
    return json.loads((ROOT / f"data/{name}_gold.json").read_text())


def environment():
    health = model.health()
    return {
        "dataset": corpus.integrity()["dataset_hash"],
        "references": corpus.digest(
            {s: references(s) for s in ["learning", "validation", "final"]}
        ),
        "code": corpus.digest(
            {p.name: p.read_text() for p in sorted((ROOT / "backend").glob("*.py"))}
        ),
        "dependencies": corpus.digest((ROOT / "requirements.lock.txt").read_text()),
        "model": model.MODEL,
        "digest": health["digest"],
        "options": model.OPTIONS,
        "evidence_catalog": corpus.digest(corpus.packs()),
        "retrieval": {
            "semantic": os.environ.get("SHIFT_SEMANTIC", "1") != "0",
            "embedding_model": model.EMBED_MODEL,
            "embedding_digest": health.get("embedding_digest"),
        },
    }


def score(result, reference):
    value = result.get("result")
    answered = (
        result.get("status") == "answer"
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
    numeric = bool(answered and abs(value - reference["result"]) <= 0.01)
    operands = bool(answered and result.get("operand_ids") == reference["operand_ids"])
    qualification = not reference.get("qualification_required") or bool(
        re.search(r"week|53|52", result.get("qualification", ""), re.I)
    )
    return {
        "correct": numeric and operands,
        "numeric": numeric,
        "operands": operands,
        "qualification_present": qualification,
        "review_requested": not answered,
    }


def freeze(reviewed):
    if not reviewed:
        raise ValueError(
            "Human review of figures, definitions, references and splits is required before freezing."
        )
    check = corpus.integrity()
    if not check["passed"] or not check["counts"]["final"]:
        raise ValueError(
            "A separate final group and passing split checks are required."
        )
    settings = environment()
    if not settings["digest"]:
        raise ValueError("Make the local model available before freezing its digest.")
    item = {
        "environment": settings,
        "procedures": [p for p in store.rows("procedure") if p["status"] == "accepted"],
        "history": engine.correction_history(),
        "source_review_attested": True,
    }
    identifier = store.put("freeze", item)
    store.log(
        "Experiment frozen", "Human source review attested; configuration captured"
    )
    return {"freeze_id": identifier}


def replay(split, freeze_id=None, emit=lambda *args: None):
    if split not in {"validation", "final"}:
        raise ValueError("Choose validation or final replay")
    if not corpus.integrity()["passed"]:
        raise ValueError("Resolve source overlap before evaluation")
    settings = environment()
    procedures = [p for p in store.rows("procedure") if p["status"] == "accepted"]
    history = engine.correction_history()
    first = True
    if split == "final":
        frozen = store.get("freeze", freeze_id)
        if frozen["environment"] != settings:
            raise ValueError("Code, model, data or settings changed after freezing.")
        previous = [e for e in store.rows("evaluation") if e["split"] == "final"]
        if any(e.get("freeze_id") == freeze_id for e in previous):
            raise ValueError(
                "This freeze has already exposed final cases, including interrupted runs."
            )
        first = not previous
        procedures, history = frozen["procedures"], frozen["history"]
    payload = {
        "split": split,
        "freeze_id": freeze_id,
        "environment": settings,
        "status": "running",
        "first_final_exposure": first if split == "final" else None,
        "procedure_count": len(procedures),
        "correction_count": len(history),
        "rows": [],
    }
    eid = store.put("evaluation", payload)
    refs = references(split)
    try:
        for i, case in enumerate(corpus.cases(split)):
            modes = ["baseline", "history", "lessons"]
            modes = modes[i % 3 :] + modes[: i % 3]
            for mode in modes:
                emit(
                    "evaluate",
                    f"{i+1}/{len(corpus.cases(split))} · {case['company']} · {mode}",
                )
                result = engine.analyze(case, mode, procedures, history)
                payload["rows"].append(
                    {
                        "case_id": case["id"],
                        "mode": mode,
                        "score": score(result, refs[case["id"]]),
                        "result": result,
                    }
                )
                store.put("evaluation", payload, eid)
        payload["metrics"] = {}
        for mode in ["baseline", "history", "lessons"]:
            rows = [r for r in payload["rows"] if r["mode"] == mode]
            payload["metrics"][mode] = {
                "correct": sum(r["score"]["correct"] for r in rows),
                "cases": len(rows),
                "review_requests": sum(r["score"]["review_requested"] for r in rows),
                "mean_seconds": (
                    round(sum(r["result"]["seconds"] for r in rows) / len(rows), 2)
                    if rows
                    else 0
                ),
            }
        paired = []
        for case in corpus.cases(split):
            scores = {
                r["mode"]: r["score"]["correct"]
                for r in payload["rows"]
                if r["case_id"] == case["id"]
            }
            paired.append((scores["baseline"], scores["lessons"]))
        payload["gains"] = sum(not a and b for a, b in paired)
        payload["regressions"] = sum(a and not b for a, b in paired)
        payload["status"] = "complete"
    except Exception:
        payload["status"] = "interrupted"
        store.put("evaluation", payload, eid)
        raise
    store.put("evaluation", payload, eid)
    from .observability import record

    metrics = {
        mode + "_" + key: value
        for mode, values in payload["metrics"].items()
        for key, value in values.items()
    }
    metrics.update(gains=payload["gains"], regressions=payload["regressions"])
    payload["tracking"] = record(
        eid,
        metrics,
        {
            "split": split,
            "model": model.MODEL,
            "model_digest": settings["digest"] or "unavailable",
            "procedures": len(procedures),
            "corrections": len(history),
            "dataset_hash": settings["dataset"],
        },
    )
    store.put("evaluation", payload, eid)
    store.log(
        "Replay complete",
        f"{split}: {payload['gains']} gains, {payload['regressions']} regressions",
    )
    return {"evaluation_id": eid}
