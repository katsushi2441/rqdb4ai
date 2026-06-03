from __future__ import annotations

import os
from typing import Any

from redis import Redis
from rq import Queue, Worker
from rq.job import Job
from rq.registry import (
    CanceledJobRegistry,
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from serializers import serialize_job


DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def redis_url() -> str:
    return os.environ.get("RQDB4AI_REDIS_URL", "redis://127.0.0.1:6379/0")


def connection() -> Redis:
    return Redis.from_url(redis_url())


def queue_names() -> list[str]:
    conn = connection()
    configured_names: set[str] = set()
    configured = os.environ.get("RQDB4AI_QUEUES", "").strip()
    if configured:
        configured_names.update(name.strip() for name in configured.split(",") if name.strip())
    active_names: set[str] = set()
    for worker in Worker.all(connection=conn):
        try:
            if worker.get_current_job():
                active_names.update(q.name for q in worker.queues if q.name != "auto")
        except Exception:
            pass
    names: set[str] = set(configured_names) | active_names
    for queue in Queue.all(connection=conn):
        name = queue.name
        if name == "auto" and name not in configured_names:
            continue
        summary = queue_summary(name)
        has_jobs = any(
            int(summary.get(key, 0) or 0) > 0
            for key in ("queued", "started", "deferred", "scheduled")
        )
        if has_jobs:
            names.add(name)
    return sorted(names)


def job_queue_names() -> list[str]:
    conn = connection()
    names: set[str] = set(q.name for q in Queue.all(connection=conn) if q.name != "auto")
    for worker in Worker.all(connection=conn):
        names.update(q.name for q in worker.queues if q.name != "auto")
    return sorted(names)


def get_queue(name: str) -> Queue:
    return Queue(name, connection=connection())


def registries(queue: Queue) -> dict[str, Any]:
    return {
        "queued": queue,
        "started": StartedJobRegistry(queue=queue),
        "deferred": DeferredJobRegistry(queue=queue),
        "scheduled": ScheduledJobRegistry(queue=queue),
        "finished": FinishedJobRegistry(queue=queue),
        "failed": FailedJobRegistry(queue=queue),
        "canceled": CanceledJobRegistry(queue=queue),
    }


def queue_summary(name: str) -> dict[str, Any]:
    queue = get_queue(name)
    regs = registries(queue)
    failed_ids = list(regs["failed"].get_job_ids())
    stopped = 0
    failed = 0
    for job_id in failed_ids:
        try:
            job = Job.fetch(job_id, connection=connection())
            if str(job.get_status(refresh=False)).lower().endswith("stopped"):
                stopped += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return {
        "name": name,
        "type": "history_queue",
        "queued": queue.count,
        "started": len(regs["started"]),
        "deferred": len(regs["deferred"]),
        "scheduled": len(regs["scheduled"]),
        "finished": len(regs["finished"]),
        "failed": failed,
        "stopped": stopped,
        "canceled": len(regs["canceled"]),
    }


def execution_queue_summary(name: str) -> dict[str, Any]:
    queue = get_queue(name)
    regs = registries(queue)
    return {
        "name": name,
        "type": "execution_queue",
        "queued": queue.count,
        "started": len(regs["started"]),
        "deferred": len(regs["deferred"]),
        "scheduled": len(regs["scheduled"]),
    }


def all_queue_summaries() -> list[dict[str, Any]]:
    return [execution_queue_summary(name) for name in queue_names()]


def history_queue_summaries() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for name in job_queue_names():
        summary = queue_summary(name)
        summaries.append(summary)
    return summaries


def history_totals(queues: list[dict[str, Any]] | None = None) -> dict[str, int]:
    source = queues if queues is not None else history_queue_summaries()
    keys = ("queued", "started", "deferred", "scheduled", "finished", "failed", "stopped", "canceled")
    return {key: sum(int(queue.get(key, 0) or 0) for queue in source) for key in keys}


def list_workers() -> list[dict[str, Any]]:
    workers = Worker.all(connection=connection())
    out = []
    for worker in workers:
        current_job = None
        try:
            job = worker.get_current_job()
            current_job = job.id if job else None
        except Exception:
            current_job = None
        out.append({
            "name": worker.name,
            "state": getattr(worker.get_state(), "value", str(worker.get_state())),
            "queues": [q.name for q in worker.queues],
            "current_job_id": current_job,
            "last_heartbeat": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
            "birth_date": worker.birth_date.isoformat() if worker.birth_date else None,
        })
    return out


def _job_ids_for(queue: Queue, status: str, offset: int, limit: int) -> list[str]:
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    regs = registries(queue)
    if status in ("", "queued"):
        jobs = queue.get_job_ids(offset=offset, length=limit)
        return list(jobs)
    if status not in regs:
        return []
    return list(regs[status].get_job_ids(offset, limit))


def list_jobs(queue_name: str | None, status: str | None, limit: int, offset: int) -> dict[str, Any]:
    names = [queue_name] if queue_name else job_queue_names()
    jobs: list[dict[str, Any]] = []
    for name in names:
        queue = get_queue(name)
        if status in (None, "", "all"):
            statuses = ["queued", "started", "failed", "stopped", "finished", "deferred", "scheduled", "canceled"]
        else:
            statuses = [status]
        for st in statuses:
            registry_status = "failed" if st == "stopped" else st
            for job_id in _job_ids_for(queue, registry_status, offset, limit):
                try:
                    job = Job.fetch(job_id, connection=connection())
                    item = serialize_job(job, detail=False)
                    if st == "failed" and item.get("status") == "stopped":
                        continue
                    if st == "stopped" and item.get("status") != "stopped":
                        continue
                    jobs.append(item)
                except Exception as exc:
                    jobs.append({"id": job_id, "queue": name, "status": st, "error": {"message": str(exc)}})
    jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"jobs": jobs[: max(1, min(limit, MAX_LIMIT))], "limit": limit, "offset": offset}


def list_work_items(limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Return unfinished work, not just Redis queue backlog.

    RQ queue counts only cover jobs still waiting/running inside RQ. A job may
    finish after it triggers an external process; that external work is still
    unfinished from the dashboard's point of view.
    """
    live_statuses = {"queued", "started", "deferred", "scheduled"}
    jobs = list_jobs(None, "all", max(1, min(limit, MAX_LIMIT)), 0).get("jobs", [])
    work_items: list[dict[str, Any]] = []
    external_by_key: dict[str, dict[str, Any]] = {}
    for item in jobs:
        lifecycle = item.get("lifecycle") or {}
        rq_status = str(item.get("status") or "")
        is_rq_live = rq_status in live_statuses
        is_external_open = lifecycle.get("terminal") is False
        if is_rq_live:
            item["work_scope"] = "rq_live"
            work_items.append(item)
            continue
        if is_external_open:
            task = item.get("task") or {}
            key_parts = [
                str(task.get("resource_key") or ""),
                str(task.get("name") or ""),
                str(task.get("project") or ""),
                str(task.get("kind") or ""),
                str(task.get("source") or ""),
            ]
            key = "|".join(key_parts)
            item["work_scope"] = "external_unconfirmed"
            item["work_key"] = key
            current = external_by_key.get(key)
            if current is None or str(item.get("created_at") or "") > str(current.get("created_at") or ""):
                external_by_key[key] = item
    work_items.extend(external_by_key.values())
    work_items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return work_items[: max(1, min(limit, MAX_LIMIT))]


def fetch_job(job_id: str) -> Job:
    return Job.fetch(job_id, connection=connection())


def requeue_job(job_id: str) -> dict[str, Any]:
    job = fetch_job(job_id)
    queue_name = job.origin
    queue = get_queue(queue_name)
    failed = FailedJobRegistry(queue=queue)
    if job_id in failed:
        failed.requeue(job_id)
        return {"ok": True, "job_id": job_id, "queue": queue_name, "action": "requeue"}
    queue.enqueue_job(job)
    return {"ok": True, "job_id": job_id, "queue": queue_name, "action": "enqueue_job"}


def delete_job(job_id: str) -> dict[str, Any]:
    job = fetch_job(job_id)
    queue_name = job.origin
    job.delete()
    return {"ok": True, "job_id": job_id, "queue": queue_name, "action": "delete"}


def cancel_job(job_id: str) -> dict[str, Any]:
    job = fetch_job(job_id)
    job.cancel()
    return {"ok": True, "job_id": job_id, "queue": job.origin, "action": "cancel"}
