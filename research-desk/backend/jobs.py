"""One bounded local worker with persistent status; interrupted work is explicit."""

import threading
from concurrent.futures import ThreadPoolExecutor
from . import store

POOL = ThreadPoolExecutor(max_workers=1)
BUSY = threading.Lock()


def recover():
    for job in store.rows("job"):
        if job["status"] in {"queued", "running"}:
            store.update(
                "job",
                job["id"],
                status="interrupted",
                message="The app restarted. Start a new run; completed artifacts remain saved.",
            )
    for run in store.rows("evaluation"):
        if run["status"] == "running":
            store.update("evaluation", run["id"], status="interrupted")


def submit(title, operation, kind="task", payload=None, with_id=False):
    if not BUSY.acquire(blocking=False):
        raise ValueError("A local task is already running. Wait for it to finish.")
    try:
        identifier = store.put(
            "job",
            {
                "title": title,
                "status": "queued",
                "stage": "queued",
                "message": "Waiting for the local worker",
                "events": [],
                "result": None,
                "kind": kind,
                "payload": payload,
            },
        )
        POOL.submit(work, identifier, operation, with_id)
    except BaseException:
        BUSY.release()
        raise
    return {"job_id": identifier}


def emit(identifier, stage, message):
    job = store.get("job", identifier)
    store.update(
        "job",
        identifier,
        status="running",
        stage=stage,
        message=message,
        events=job["events"] + [{"stage": stage, "message": message}],
    )


def work(identifier, operation, with_id=False):
    event = lambda stage, message: emit(identifier, stage, message)

    try:
        event("start", "Starting local work")
        result = operation(event, identifier) if with_id else operation(event)
        waiting = isinstance(result, dict) and result.get("status") == "waiting_review"
        store.update(
            "job",
            identifier,
            status="waiting_review" if waiting else "complete",
            stage="review" if waiting else "complete",
            message=(
                "Research saved. Human review is required."
                if waiting
                else "Work saved. Inspect the result and its evidence."
            ),
            result=result,
        )
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, (ValueError, OSError))
            else "Local task failed. No result was approved; inspect the terminal and retry."
        )
        store.update(
            "job", identifier, status="failed", stage="failed", message=message
        )
    finally:
        BUSY.release()


def analysis(payload):
    from . import workflow

    title = (
        "Research assignment"
        if not payload.get("case")
        else "Analyze " + payload["case"]["company"]
    )
    return submit(
        title,
        lambda emit, jid: workflow.execute(jid, payload),
        kind="analysis",
        payload=payload,
        with_id=True,
    )


def retry(identifier):
    from . import workflow

    job = store.get("job", identifier)
    if job.get("kind") != "analysis" or job["status"] not in {"failed", "interrupted"}:
        raise ValueError(
            "Only interrupted or failed research can resume its checkpoint"
        )
    if not BUSY.acquire(blocking=False):
        raise ValueError("Wait for the current local task to finish")
    store.update(
        "job", identifier, status="queued", message="Resuming the saved checkpoint"
    )
    POOL.submit(work, identifier, lambda emit: workflow.execute(identifier))
    return {"job_id": identifier}


def review_attempt(identifier, status):
    from . import workflow

    if not BUSY.acquire(blocking=False):
        raise ValueError("Wait for the running local task before recording a review")
    scheduled = False
    try:
        a = store.get("attempt", identifier)
        store.put(
            "review",
            {"attempt_id": identifier, "status": status},
            "review_" + identifier,
        )
        store.log("Analysis reviewed", status + " · " + identifier)
        if a.get("workflow_id"):
            job = store.get("job", a["workflow_id"])
            if job["status"] == "waiting_review":
                ids = {r["id"] for r in job["result"]["results"]}
                decisions = {
                    r["attempt_id"]: r["status"]
                    for r in store.rows("review")
                    if r["attempt_id"] in ids
                }
                if set(decisions) == ids:
                    store.update(
                        "job",
                        job["id"],
                        status="queued",
                        message="Recording the completed human review",
                    )
                    POOL.submit(
                        work,
                        job["id"],
                        lambda emit: workflow.execute(job["id"], resume=decisions),
                    )
                    scheduled = True
        return {"status": status}
    finally:
        if not scheduled:
            BUSY.release()
