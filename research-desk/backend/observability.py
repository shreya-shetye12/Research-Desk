"""Local MLflow traces and experiment metrics. No hosted tracking service."""

import os
import threading
from contextlib import contextmanager
from .store import RUNTIME

_LOCK = threading.Lock()
_READY = False


def setup():
    global _READY
    if os.environ.get("SHIFT_TRACKING", "1") == "0":
        return None
    import mlflow

    with _LOCK:
        if not _READY:
            mlflow.set_tracking_uri("sqlite:///" + str(RUNTIME / "mlflow.db"))
            if mlflow.get_experiment_by_name('SHIFT hackathon learning') is None:
                mlflow.create_experiment('SHIFT hackathon learning',artifact_location=str(RUNTIME/'artifacts'))
            mlflow.set_experiment("SHIFT hackathon learning")
            _READY = True
    return mlflow


@contextmanager
def span(name, inputs=None):
    mlflow = setup()
    if mlflow is None:
        yield None
        return
    with mlflow.start_span(name=name) as active:
        if inputs is not None:
            active.set_inputs(inputs)
        yield active


def record_evaluation(identifier, metrics, parameters):
    mlflow = setup()
    if mlflow is None:
        return
    with mlflow.start_run(run_name=identifier) as run:
        mlflow.log_params(parameters)
        mlflow.log_metrics(
            {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
        )
        return run.info.run_id


def record(identifier, metrics, parameters):
    """Tracking failures remain visible without discarding computed evaluation results."""
    try:
        return {
            "run_id": record_evaluation(identifier, metrics, parameters),
            "enabled": os.environ.get("SHIFT_TRACKING", "1") != "0",
        }
    except Exception as error:
        return {
            "error": type(error).__name__ + ": local MLflow recording failed",
            "enabled": True,
        }
