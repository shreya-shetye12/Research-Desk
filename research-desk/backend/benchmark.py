"""Explicit development benchmark; never teaches or approves an app procedure."""
import copy
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from . import bindings, corpus, engine, evaluation, model, observability, store
from .models import Selection

ROOT = store.ROOT


def load(name):
    return json.loads((ROOT / "data" / name).read_text())


def checkpoint(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def in_scope(case, rule):
    return all(case[k] == rule[k] for k in ["company", "report", "task"]) and bindings.scope_matches(rule["binding"], case)


def summarize(rows):
    def counts(items):
        values = {"cases": len(items)}
        for mode in ["baseline", "reference_rule"]:
            values[mode] = {"correct": sum(r[mode]["score"]["correct"] for r in items), "cases": len(items), "errors": sum(bool(r[mode].get("error")) for r in items), "review_requests": sum(r[mode]["score"]["review_requested"] for r in items)}
        values["gains"] = sum(not r["baseline"]["score"]["correct"] and r["reference_rule"]["score"]["correct"] for r in items)
        values["regressions"] = sum(r["baseline"]["score"]["correct"] and not r["reference_rule"]["score"]["correct"] for r in items)
        return values
    result = {"overall": counts(rows), "distinct_calculations": counts([r for r in rows if r["category"] in {"original", "additional_calculation"}]), "applicable": counts([r for r in rows if r["applicable"]]), "boundary": counts([r for r in rows if not r["applicable"]])}
    result["by_category"] = {k: counts([r for r in rows if r["category"] == k]) for k in sorted({r["category"] for r in rows})}
    result["by_source"] = {k: counts([r for r in rows if r["source_group"] == k]) for k in sorted({r["source_group"] for r in rows})}
    return result


def invoke(case, condition, rule, answer):
    started = time.monotonic()
    try:
        with observability.span("benchmark." + condition, {"case_id": case["id"], "condition": condition}) as trace:
            if condition == "baseline":
                result = engine.analyze(case, "baseline", [], [])
            else:
                # Reuse the application's analyst/binding/auditor/calculator.
                # The rule is explicit experimental input, NOT an accepted record.
                retrieval = engine.retrieve_case(case)
                memory = [engine.public(rule)] if in_scope(case, rule) else []
                proposal = model.chat(engine.ANALYST, {"evidence": case, "memory": memory}, Selection)
                selection = bindings.apply(case, proposal, memory)
                checked = engine.audit(case, selection)
                result = engine.finalize(case, selection, memory, checked, time.monotonic() - started, retrieval)
            score = evaluation.score(result, answer)
            if trace:
                trace.set_outputs({"result": result, "score": score})
            return {"result": result, "score": score}
    except Exception as error:
        return {"error": {"type": type(error).__name__, "message": str(error)}, "score": {"correct": False, "numeric": False, "operands": False, "qualification_present": False, "review_requested": True}}


def run(path, resume=False):
    store.initialize()
    health = model.health()
    if not health.get("ready"):
        raise ValueError(f"Start Ollama and install {model.MODEL}; current health: {health}")
    check = corpus.integrity()
    if not check["passed"] or check["counts"]["validation"] != 50:
        raise ValueError("A passing 50-case development suite is required")
    manifest, fixture = load("validation_manifest.json"), load("comparison_rule.json")
    if fixture["provenance"]["human_approved"] or "status" in fixture["rule"]:
        raise ValueError("This runner requires an explicitly unapproved evaluation-only rule")
    settings = evaluation.environment()
    fingerprint = corpus.digest({"environment": settings, "manifest": manifest, "comparison_rule": fixture, "source_archive": json.loads((ROOT / "SOURCE_PROVENANCE.json").read_text())["source_archive_sha256"]})
    path = Path(path).resolve()
    if path.exists():
        if not resume:
            raise ValueError("Output exists; choose a fresh path or pass --resume")
        payload = json.loads(path.read_text())
        if payload["fingerprint"] != fingerprint:
            raise ValueError("Cannot resume after code, model, settings, fixtures or data changed")
    else:
        payload = {"application": "Research Desk", "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(), "environment": settings, "fingerprint": fingerprint, "comparison_rule": fixture, "suite": {k: v for k, v in manifest.items() if k != "cases"}, "method": "Paired development replay with real local model calls. Eight scoped cases execute both conditions in alternating order; unchanged out-of-scope empty-memory branches reuse the actual baseline result, explicitly marked. The reference rule is derived only from learning evidence and is not human-approved or stored as an accepted procedure. No final inference or teaching from validation answers.", "rows": []}
    done = {r["case_id"] for r in payload["rows"]}
    references = evaluation.references("validation")
    rule = fixture["rule"]
    for index, case in enumerate(corpus.cases("validation")):
        if case["id"] in done:
            continue
        row = {"case_id": case["id"], "source_group": case["group"], **manifest["cases"][case["id"]], "applicable": in_scope(case, rule)}
        if row["applicable"]:
            order = ["baseline", "reference_rule"] if index % 2 == 0 else ["reference_rule", "baseline"]
            for condition in order:
                print(f"{index+1}/50 {case['id']} [{condition}]", flush=True)
                row[condition] = invoke(case, condition, rule, references[case["id"]])
        else:
            print(f"{index+1}/50 {case['id']} [baseline; rule out of scope]", flush=True)
            row["baseline"] = invoke(case, "baseline", rule, references[case["id"]])
            row["reference_rule"] = copy.deepcopy(row["baseline"])
            row["reference_rule"]["reused"] = "Same evidence, empty memory, model and options; unchanged execution branch"
        payload["rows"].append(row)
        payload["metrics"] = summarize(payload["rows"])
        checkpoint(path, payload)
        print(f"  correctness {row['baseline']['score']['correct']} -> {row['reference_rule']['score']['correct']}", flush=True)
    payload["status"] = "complete"
    payload["finished_utc"] = datetime.now(timezone.utc).isoformat()
    overall = payload["metrics"]["overall"]
    metrics = {f"{mode}_{key}": value for mode in ["baseline", "reference_rule"] for key, value in overall[mode].items()}
    metrics.update(gains=overall["gains"], regressions=overall["regressions"])
    payload["tracking"] = observability.record("research-desk-development-" + fingerprint[:12], metrics, {"model": model.MODEL, "model_digest": health["digest"], "fingerprint": fingerprint, "comparison": "learning-derived reference rule; not human-approved", "source_groups": 3, "distinct_calculations": 30})
    checkpoint(path, payload)
    if payload["tracking"].get("run_id"):
        import mlflow
        with mlflow.start_run(run_id=payload["tracking"]["run_id"]):
            mlflow.log_artifact(str(path), "evaluation")
            for name in ["validation_manifest.json", "comparison_rule.json"]:
                mlflow.log_artifact(str(ROOT / "data" / name), "provenance")
        mlflow.flush_trace_async_logging()
    return payload


def report(path):
    path = Path(path)
    payload = json.loads(path.read_text())
    if payload["status"] != "complete" or len(payload["rows"]) != 50:
        raise ValueError("A completed real 50-case evaluation is required")
    if payload["metrics"] != summarize(payload["rows"]):
        raise ValueError("Stored metrics disagree with per-case outcomes")
    references = evaluation.references("validation")
    cases = {c["id"]: c for c in corpus.cases("validation")}
    fields = ["case_id", "category", "parent", "source_group", "applicable", "question", "expected_value", "expected_operands", "baseline_correct", "reference_rule_correct", "baseline_value", "reference_rule_value", "baseline_operands", "reference_rule_operands", "baseline_error", "reference_rule_error", "shared_branch"]
    with path.with_name("per_case.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in payload["rows"]:
            ref = references[row["case_id"]]
            record = {k: row[k] for k in fields[:5]}
            record.update(question=cases[row["case_id"]]["question"], expected_value=ref["result"], expected_operands=json.dumps(ref["operand_ids"]), shared_branch=bool(row["reference_rule"].get("reused")))
            for mode in ["baseline", "reference_rule"]:
                outcome = row[mode]
                record.update({mode + "_correct": outcome["score"]["correct"], mode + "_value": outcome.get("result", {}).get("result"), mode + "_operands": json.dumps(outcome.get("result", {}).get("operand_ids", [])), mode + "_error": json.dumps(outcome.get("error"))})
            writer.writerow(record)
    overall = payload["metrics"]["overall"]
    a, b = overall["baseline"]["correct"], overall["reference_rule"]["correct"]
    lines = ["# Research Desk: measured development evaluation", "", f"**Baseline {a}/50 ({a*2}%) -> reference-rule comparison {b}/50 ({b*2}%). Change: {(b-a)*2:+d} percentage points.**", "", "This is a new run on the supplied current codebase. Earlier generated code and results were not imported. The comparison rule is newly constructed from this checkout's learning evidence; it is not an approved or learned-from-validation application procedure.", "", "| Slice | Cases | Baseline correct | Reference-rule correct | Gains | Regressions |", "|---|---:|---:|---:|---:|---:|"]
    slices = [("Overall", overall), ("Distinct calculations", payload["metrics"]["distinct_calculations"]), ("Applicable", payload["metrics"]["applicable"]), ("Out of scope", payload["metrics"]["boundary"])] + list(payload["metrics"]["by_category"].items()) + list(payload["metrics"]["by_source"].items())
    for title, values in slices:
        lines.append(f"| {title} | {values['cases']} | {values['baseline']['correct']} | {values['reference_rule']['correct']} | {values['gains']} | {values['regressions']} |")
    lines += ["", "## Protocol and limits", "", "- 50 authored development cases = 30 distinct calculations + 20 correlated row-order/opaque-ID variants, over only three source groups. This is not 50 independent documents or a held-out final benchmark.", "- Original 12 cases and their references are unchanged. Learning and reserved-final sets remain unchanged; no final model inference is performed. Prepared source figures retain their original review status; no new human source review is claimed.", "- Correctness requires exact ordered source operand IDs AND a numeric result within 0.01. Requested reviews and runtime failures count as incorrect. Fiscal-week qualification is scored separately using the existing evaluator's text heuristic.", "- Eight scoped cases run both real inference conditions with alternating order. Outside-scope branches reuse the real baseline result because model inputs and execution are identical. Each shared row is labeled; zero boundary regressions are guaranteed by unchanged execution, not independent reruns.", "- The intervention combines reference-procedure text with deterministic label binding and model auditing. It does not establish model-weight learning, a text-only memory benefit or a new human approval. The normal application's approval gate remains intact; this runner never stores its rule in the accepted-procedure ledger.", "- Single fixed-seed run; correlated cases and only three source groups. No generalization, statistical significance, production-readiness or financial-advice reliability claim is supported.", f"- Model: `{payload['environment']['model']}`; digest `{payload['environment']['digest']}`.", f"- Model options: `{json.dumps(payload['environment']['options'])}`.", f"- Fingerprint: `{payload['fingerprint']}`.", f"- MLflow: `{json.dumps(payload['tracking'])}`.", f"- Start/end UTC: {payload['started_utc']} / {payload['finished_utc']}.", "", "## Resume wording supported by this run", "", f"> Expanded Research Desk's development evaluation to 50 cases; measured {a*2}% baseline correctness versus {b*2}% with a scoped source-binding reference rule, using MLflow traces and paired failure analysis.", "", "Describe the application as approval-gated; do not describe this unapproved comparison rule as human-approved memory.", "", "## Remaining failures", ""]
    for row in payload["rows"]:
        if not row["reference_rule"]["score"]["correct"]:
            value = row["reference_rule"].get("result", {})
            lines.append(f"- `{row['case_id']}`: status `{value.get('status','error')}`; chosen `{value.get('operand_ids',[])}`; expected `{references[row['case_id']]['operand_ids']}`; runtime error `{row['reference_rule'].get('error')}`.")
    path.with_name("RESULTS.md").write_text("\n".join(lines) + "\n")
    return {"baseline": a, "reference_rule": b, "cases": 50}
