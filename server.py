from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from auth import TokenIdentity, require_identity, require_role
from rq_client import (
    all_queue_summaries,
    cancel_job,
    connection,
    delete_job,
    fetch_job,
    get_queue,
    history_queue_summaries,
    history_totals,
    list_jobs,
    list_work_items,
    list_workers,
    queue_names,
    redis_url,
    requeue_job,
)
from serializers import serialize_job


app = FastAPI(
    title="Kurage RQ Dashboard for AI",
    version="0.1.0",
    description="Generic RQ/Redis job dashboard API for humans and AI agents.",
)


def redis_error_payload(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": "redis_unavailable", "detail": str(exc)}


class EnqueueRequest(BaseModel):
    queue: str = Field(default="default")
    function: str = Field(default="sample_jobs.echo_job")
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    timeout: int | None = Field(default=None)
    result_ttl: int = Field(default=86400)
    failure_ttl: int = Field(default=604800)


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.strip()).strip("-").lower()


def queue_class_from_source(source: Any) -> str:
    text = str(source or "").strip().lower()
    if text in {"web", "web_online", "web_manual", "ui", "admin", "manual", "interactive"}:
        return "web"
    if text in {"worker", "worker_auto", "cron", "batch", "scheduler", "background"}:
        return "worker"
    return "worker"


def configured_execution_queues() -> list[str]:
    raw = os.environ.get("RQDB4AI_QUEUES", "").strip()
    return [name.strip() for name in raw.split(",") if name.strip()]


def default_queue_for_class(queue_class: str) -> str:
    configured = configured_execution_queues()
    suffix = f"-{queue_class}"
    for name in configured:
        if name.endswith(suffix):
            return name
    if configured:
        return configured[0]
    return "default"


def resolve_queue(req: EnqueueRequest) -> tuple[str, dict[str, Any]]:
    meta = dict(req.meta or {})
    kwargs = dict(req.kwargs or {})
    queue = (req.queue or "").strip()

    source = meta.get("source") or kwargs.get("source")
    queue_class = meta.get("queue_class") or kwargs.get("queue_class") or queue_class_from_source(source)
    priority_class = meta.get("priority_class") or ("interactive" if queue_class == "web" else "background")
    resource = meta.get("resource") or kwargs.get("resource")
    ollama_host = meta.get("ollama_host") or kwargs.get("ollama_host")
    ollama_model = meta.get("ollama_model") or meta.get("model") or kwargs.get("ollama_model") or kwargs.get("model")

    meta["source"] = source
    meta["queue_class"] = queue_class
    meta["priority_class"] = priority_class

    if resource == "ollama" and ollama_host:
        host_key = slug(str(ollama_host))
        if ollama_model:
            meta["resource_key"] = meta.get("resource_key") or f"ollama:{ollama_host}:{ollama_model}"
        if queue in {"", "auto", "ollama", "resource"}:
            queue = f"ollama-{host_key}-{queue_class}"

    if queue in {"", "auto"}:
        queue = default_queue_for_class(queue_class)

    if not queue:
        queue = "default"
    return queue, meta


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    url = redis_url()
    password = os.environ.get("RQDB4AI_REDIS_PASSWORD", "")
    data = {
        "ok": True,
        "service": "rqdb4ai",
        "redis_url": url.replace(password, "***") if password else url,
    }
    try:
        data["redis_ping"] = bool(connection().ping())
    except Exception as exc:
        data["ok"] = False
        data["redis_ping"] = False
        data["error"] = str(exc)
    return data


@app.get("/api/capabilities")
def capabilities(identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    return {
        "ok": True,
        "project": "Kurage RQ Dashboard for AI",
        "folder": "rqdb4ai",
        "role": identity.role,
        "features": [
            "queue_summary",
            "worker_summary",
            "job_list",
            "job_detail",
            "requeue_failed_job",
            "cancel_job",
            "delete_job",
            "enqueue_sample_or_registered_function",
        ],
        "statuses": ["queued", "started", "deferred", "scheduled", "finished", "failed", "stopped", "canceled"],
    }


@app.get("/api/summary")
def summary(identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    try:
        execution_queues = all_queue_summaries()
        history_queues = history_queue_summaries()
        work_items = list_work_items()
        workers = list_workers()
    except Exception as exc:
        return redis_error_payload(exc)
    live_failed = sum(q.get("failed", 0) for q in execution_queues)
    live_stopped = sum(q.get("stopped", 0) for q in execution_queues)
    live_started = sum(q.get("started", 0) for q in execution_queues)
    live_queued = sum(q.get("queued", 0) for q in execution_queues)
    live_deferred = sum(q.get("deferred", 0) for q in execution_queues)
    live_scheduled = sum(q.get("scheduled", 0) for q in execution_queues)
    totals = history_totals(history_queues)
    external_unconfirmed = sum(1 for item in work_items if item.get("work_scope") == "external_unconfirmed")
    suggestions = []
    if totals["failed"]:
        suggestions.append({"action": "inspect_failed", "count": totals["failed"], "risk": "low"})
    if totals["stopped"]:
        suggestions.append({"action": "inspect_stopped", "count": totals["stopped"], "risk": "low"})
    if live_queued and not workers:
        suggestions.append({"action": "start_worker", "count": live_queued, "risk": "medium"})
    text = (
        f"{len(execution_queues)} execution queues, {len(history_queues)} history queues, "
        f"{len(workers)} workers, {len(work_items)} unfinished work items, "
        f"{live_queued} queued, {live_started} running, "
        f"{totals['finished']} finished, {totals['failed']} failed, {totals['stopped']} stopped."
    )
    return {
        "ok": True,
        "summary": text,
        "queues": execution_queues,
        "execution_queues": execution_queues,
        "history_queues": history_queues,
        "work_items": work_items,
        "totals": {
            "live": {
                "queued": live_queued,
                "started": live_started,
                "deferred": live_deferred,
                "scheduled": live_scheduled,
                "failed": live_failed,
                "stopped": live_stopped,
            },
            "work": {
                "active": len(work_items),
                "rq_live": live_queued + live_started + live_deferred + live_scheduled,
                "external_unconfirmed": external_unconfirmed,
            },
            "history": totals,
        },
        "workers": workers,
        "suggested_actions": suggestions,
    }


@app.get("/api/queues")
def queues(identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    try:
        return {"ok": True, "queues": all_queue_summaries()}
    except Exception as exc:
        return redis_error_payload(exc)


@app.get("/api/workers")
def workers(identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    try:
        return {"ok": True, "workers": list_workers()}
    except Exception as exc:
        return redis_error_payload(exc)


@app.get("/api/jobs")
def jobs(
    queue: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    identity: TokenIdentity = Depends(require_identity),
) -> dict[str, Any]:
    try:
        return {"ok": True, **list_jobs(queue, status, limit, offset)}
    except Exception as exc:
        return redis_error_payload(exc)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    try:
        job = fetch_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "job": serialize_job(job, detail=True)}


@app.get("/api/jobs/{job_id}/logs")
def job_logs(job_id: str, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    try:
        job = fetch_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "job_id": job_id, "exc_info": getattr(job, "exc_info", None), "meta": getattr(job, "meta", {})}


@app.post("/api/jobs/{job_id}/requeue")
def job_requeue(job_id: str, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    require_role(identity, "operate")
    return requeue_job(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    require_role(identity, "operate")
    return cancel_job(job_id)


@app.delete("/api/jobs/{job_id}")
def job_delete(job_id: str, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    require_role(identity, "operate")
    return delete_job(job_id)


@app.post("/api/enqueue")
def enqueue(req: EnqueueRequest, identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    require_role(identity, "operate")
    if not req.function.startswith("sample_jobs."):
        require_role(identity, "admin")
    queue_name, meta = resolve_queue(req)
    queue = get_queue(queue_name)
    job = queue.enqueue(
        req.function,
        *req.args,
        **req.kwargs,
        meta=meta,
        job_timeout=req.timeout,
        result_ttl=req.result_ttl,
        failure_ttl=req.failure_ttl,
    )
    return {"ok": True, "job": serialize_job(job, detail=False)}


@app.post("/api/sample/enqueue")
def enqueue_sample(identity: TokenIdentity = Depends(require_identity)) -> dict[str, Any]:
    require_role(identity, "operate")
    queue_name = os.environ.get("RQDB4AI_SAMPLE_QUEUE", "rqdb4ai-sample")
    queue = get_queue(queue_name)
    job = queue.enqueue(
        "sample_jobs.echo_job",
        message="Kurage RQ Dashboard for AI sample job",
        meta={"project": "rqdb4ai", "kind": "sample"},
        result_ttl=86400,
        failure_ttl=604800,
    )
    return {"ok": True, "job": serialize_job(job, detail=False)}


@app.post("/api/bulk/requeue")
def bulk_requeue(
    queue: str | None = None,
    status: str = "failed",
    limit: int = Query(default=50, ge=1, le=200),
    identity: TokenIdentity = Depends(require_identity),
) -> dict[str, Any]:
    require_role(identity, "admin")
    data = list_jobs(queue, status, limit, 0)
    results = []
    for item in data["jobs"]:
        try:
            results.append(requeue_job(item["id"]))
        except Exception as exc:
            results.append({"ok": False, "job_id": item.get("id"), "error": str(exc)})
    return {"ok": True, "results": results}
