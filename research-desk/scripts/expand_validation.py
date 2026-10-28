"""Build 50 authored development cases from this checkout's existing evidence.

Retain the original twelve; enumerate eighteen other calculations; add twenty
explicit source-row/ID robustness variants. No new reports or final data are used.
"""
import copy
import hashlib
import itertools
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "data" / name).read_text())


def save(name, value):
    (ROOT / "data" / name).write_text(json.dumps(value, indent=2) + "\n")


def period_type(cell):
    return "quarterly" if "16 Weeks Ended" in cell["location"] else "annual"


def key(case, answer):
    return case["group"], case["task"], tuple(answer["operand_ids"])


def main():
    if not (ROOT / "data/validation_original.json").exists():
        save("validation_original.json", [c for c in read("cases.json") if c["split"] == "validation"])
        save("validation_original_gold.json", read("validation_gold.json"))
    original = read("validation_original.json")
    answers = read("validation_original_gold.json")
    cases = copy.deepcopy(original)
    manifest = {c["id"]: {"category": "original", "parent": c["id"]} for c in original}
    seen = {key(c, answers[c["id"]]) for c in original}
    reports = {c["group"]: c for c in original}
    for group, sample in sorted(reports.items()):
        years = sorted({cell["period"] for cell in sample["cells"]})
        kinds = sorted({period_type(cell) for cell in sample["cells"]})
        for kind, basis, task in itertools.product(kinds, ["total_revenue", "sales"], ["operating_margin", "revenue_growth"]):
            periods = [(y, y) for y in years] if task == "operating_margin" else [(b, a) for a, b in itertools.combinations(years, 2)]
            label = "Total revenue" if basis == "total_revenue" else "Sales" if sample["company"] == "Target" else "Net sales"
            for year, prior in periods:
                first_label = "Operating income" if task == "operating_margin" else label
                selected = []
                for requested_label, requested_year in [(first_label, year), (label, prior)]:
                    matches = [cell for cell in sample["cells"] if cell["label"] == requested_label and cell["period"] == requested_year and period_type(cell) == kind]
                    if len(matches) == 1:
                        selected.append(matches[0])
                if len(selected) != 2:
                    continue
                case = copy.deepcopy(sample)
                case.update(task=task, period=year, prior_period=None if task == "operating_margin" else prior, revenue_basis=basis)
                a, b = selected
                answer = {"operand_ids": [a["id"], b["id"]], "result": a["value"] / b["value"] * 100 if task == "operating_margin" else (a["value"] - b["value"]) / b["value"] * 100, "qualification_required": False}
                identity = key(case, answer)
                if identity in seen:
                    continue
                case["id"] = "dev_" + hashlib.sha256(repr(identity).encode()).hexdigest()[:12]
                scope = "annual" if kind == "annual" else "fourth-quarter (16-week)"
                case["question"] = f"Calculate {sample['company']} FY{year} {scope} {task.replace('_', ' ')} using the reported '{label}' figures."
                if task == "revenue_growth":
                    case["question"] += f" Compare with the same reporting period in FY{prior}; use reported, unadjusted growth."
                cases.append(case)
                answers[case["id"]] = answer
                manifest[case["id"]] = {"category": "additional_calculation", "parent": case["id"]}
                seen.add(identity)
    if len(cases) != 30:
        raise ValueError(f"Expected 30 distinct calculations, got {len(cases)}")
    # Source-balanced round robin, fixed before inference; not chosen for gains.
    buckets = [[c for c in cases if c["group"] == group] for group in sorted(reports)]
    parents = [c for row in itertools.zip_longest(*buckets) for c in row if c is not None][:20]
    for index, parent in enumerate(parents):
        case, answer = copy.deepcopy(parent), copy.deepcopy(answers[parent["id"]])
        category = "row_order" if index % 2 == 0 else "opaque_ids"
        case["id"] = parent["id"] + "__" + category
        if category == "row_order":
            random.Random(2026 + index).shuffle(case["cells"])
            if case["cells"] == parent["cells"]:
                case["cells"].reverse()
        else:
            mapping = {c["id"]: "row_" + hashlib.sha256((case["id"] + c["id"]).encode()).hexdigest()[:12] for c in case["cells"]}
            for cell in case["cells"]:
                cell["id"] = mapping[cell["id"]]
            answer["operand_ids"] = [mapping[x] for x in answer["operand_ids"]]
        cases.append(case)
        answers[case["id"]] = answer
        manifest[case["id"]] = {"category": category, "parent": parent["id"]}
    untouched = [c for c in read("cases.json") if c["split"] != "validation"]
    save("cases.json", untouched + cases)
    save("validation_gold.json", answers)
    save("validation_manifest.json", {"cases": manifest, "total": 50, "unique_calculations": 30, "source_groups": 3, "robustness_variants": 20, "note": "Authored development cases. Variants share evidence with their parents; not 50 independent financial reports. Existing source-review status is unchanged."})
    # A fresh evaluation-only comparison rule from this checkout's learning data.
    learning = next(c for c in untouched if c["id"] == "costco24_margin_total")
    ref = read("development_gold.json")[learning["id"]]
    cells = {c["id"]: c for c in learning["cells"]}
    first, second = [cells[i]["label"] for i in ref["operand_ids"]]
    save("comparison_rule.json", {
        "provenance": {"kind": "evaluation_only_reference_rule", "learning_case": learning["id"], "source_group": learning["group"], "human_approved": False, "note": "Constructed from learning evidence only. Never stored or activated as an accepted application procedure; no earlier generated code or historical runtime artifact imported."},
        "rule": {"id": "eval_costco_annual_total_margin", "version": 1, "company": learning["company"], "report": learning["report"], "task": learning["task"], "procedure": f"For an annual total-revenue operating margin, copy the source ID for {first} first and {second} second from the requested annual reporting period. Divide the first figure by the second and convert to percent.", "conditions": ["Same company, reporting convention, annual period and total-revenue basis."], "exclusions": "Exclude quarterly calculations, sales-basis margins and revenue growth.", "binding": {"kind": "source_label_binding", "first_label": first, "second_label": second, "period_kind": "annual", "revenue_basis": "total_revenue"}},
    })
    print("Built 50 validation cases: 12 original + 18 other calculations + 20 robustness variants.")


if __name__ == "__main__":
    main()
