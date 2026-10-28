"""Export the completed Research Desk benchmark's local tracking evidence."""
import json
import os
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
    import mlflow
    payload = json.loads((ROOT / "results/evaluation.json").read_text())
    if payload.get("status") != "complete":
        raise ValueError("Finish the evaluation before exporting evidence")
    destination = ROOT / "results/tracking"
    destination.mkdir(parents=True, exist_ok=True)
    source = ROOT / ".runtime/mlflow.db"
    mlflow.set_tracking_uri("sqlite:///" + str(source))
    experiment = mlflow.get_experiment_by_name("SHIFT hackathon learning")
    traces = mlflow.search_traces(experiment_ids=[experiment.experiment_id], max_results=1000, return_type="list", include_spans=True, flush=True)
    (destination / "traces.json").write_text(json.dumps([trace.to_dict() for trace in traces], indent=2) + "\n")
    with sqlite3.connect(source) as connection, sqlite3.connect(destination / "mlflow.db") as snapshot:
        connection.backup(snapshot)
    if (ROOT / ".runtime/artifacts").exists():
        shutil.copytree(ROOT / ".runtime/artifacts", destination / "artifacts", dirs_exist_ok=True)
    (destination / "README.md").write_text(
        "# Research Desk tracking snapshot\n\n"
        f"{len(traces)} actual case-level traces, with nested analyst/auditor spans. "
        "`traces.json` is portable. `mlflow.db` is a consistent SQLite backup; "
        "its artifact URIs retain their original absolute paths. Copies of those "
        "artifacts are included under `artifacts/`. This is benchmark evidence, "
        "not a saved approved-procedure database.\n"
    )
    print(f"Exported {len(traces)} real MLflow traces")


if __name__ == "__main__":
    main()
