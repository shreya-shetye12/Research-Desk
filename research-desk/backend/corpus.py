"""Prepared evidence only. Model-facing functions never load reference answers."""

import hashlib
import json
from .store import ROOT
from . import store


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cases(split=None):
    data = json.loads((ROOT / "data/cases.json").read_text())
    return [c for c in data if split is None or c["split"] == split]


def brief(identifier):
    item = next((c for c in cases("learning") if c["id"] == identifier), None)
    if item is None:
        raise ValueError(
            "Select an available learning brief. Reserved cases cannot be taught."
        )
    return item


def packs():
    result = {}
    for case in cases("learning"):
        key = case["group"] + ":" + case["report"]
        result.setdefault(
            key,
            {
                k: case[k]
                for k in [
                    "company",
                    "report",
                    "group",
                    "cells",
                    "notes",
                    "source_review",
                ]
            },
        )
        result[key].update(id=key, split="learning")
    documents = {d["id"]: d for d in store.rows("document")}
    for p in store.rows("pack"):
        document = documents.get(p.get("document_id"), {})
        result[p["id"]] = {**p, "name": document.get("name", p.get("name", ""))}
    return list(result.values())


def catalog():
    return [
        {
            "id": p["id"],
            "name": p.get("name", ""),
            "company": p["company"],
            "report": p["report"],
            "periods": sorted({c["period"] for c in p["cells"]}),
            "labels": sorted({c["label"] for c in p["cells"]}),
            "notes": p["notes"],
        }
        for p in packs()
    ]


def from_step(step, pack, request_context=""):
    required = {step["period"]}
    if step["task"] == "revenue_growth":
        required.add(step["prior_period"])
    if not required.issubset({c["period"] for c in pack["cells"]}):
        raise ValueError(
            "The selected report does not cover the requested fiscal periods"
        )
    basis = (
        "total revenue"
        if step["revenue_basis"] == "total_revenue"
        else "Sales excluding other revenue or membership fees"
    )
    question = (
        f"Calculate FY{step['period']} {step['task'].replace('_',' ')} using {basis}."
    )
    if step["task"] == "revenue_growth":
        question += (
            f" Compare with FY{step['prior_period']}; use reported, unadjusted figures."
        )
    return {
        **step,
        "id": "assignment_" + digest({"step": step, "pack": pack["id"]})[:16],
        "question": question,
        "request_context": request_context,
        "source_pack_id": pack["id"],
        "source_name": pack.get("name", ""),
        **{
            k: pack[k]
            for k in ["company", "report", "group", "cells", "notes", "source_review"]
        },
        "split": "learning",
    }


def integrity():
    groups, cells, issues = {}, {}, []
    for case in cases():
        split = case["split"]
        if groups.setdefault(case["group"], split) != split:
            issues.append("Source group crosses splits: " + case["group"])
        for cell in case["cells"]:
            key = (cell["company"], cell["period"], cell["value"], cell["unit"])
            if cells.setdefault(key, split) != split:
                issues.append("Repeated source figure crosses splits: " + str(key))
    return {
        "passed": not issues,
        "issues": sorted(set(issues)),
        "groups": len(groups),
        "counts": {s: len(cases(s)) for s in ["learning", "validation", "final"]},
        "dataset_hash": digest(cases()),
    }


def changes():
    """Text/schema signals, never a claim of complete semantic drift detection."""
    output = []
    evidence = packs()
    for company in sorted({p["company"] for p in evidence}):
        reports = sorted(
            [p for p in evidence if p["company"] == company],
            key=lambda p: max(c["period"] for c in p["cells"]),
        )
        for old, new in zip(reports, reports[1:]):
            a = {c["label"] for c in old["cells"]}
            b = {c["label"] for c in new["cells"]}
            if a != b or old["notes"] != new["notes"]:
                output.append(
                    {
                        "company": company,
                        "old": old["report"],
                        "new": new["report"],
                        "removed": sorted(a - b),
                        "added": sorted(b - a),
                        "old_notes": old["notes"],
                        "new_notes": new["notes"],
                    }
                )
    return output
