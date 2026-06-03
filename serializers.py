from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MAX_PREVIEW = 2000
MAX_FULL_TEXT = 120000


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def safe_text(value: Any, limit: int = MAX_PREVIEW) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, bytes):
            text = value.decode("utf-8", "replace")
        elif isinstance(value, (str, int, float, bool)):
            text = str(value)
        else:
            text = repr(value)
    except Exception as exc:
        text = f"<unserializable: {type(value).__name__}: {exc}>"
    if len(text) > limit:
        return text[:limit] + f"... <truncated {len(text) - limit} chars>"
    return text


def safe_json_value(value: Any, limit: int = MAX_FULL_TEXT) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return safe_text(value, limit) if isinstance(value, str) else value
    if isinstance(value, bytes):
        return safe_text(value, limit)
    if isinstance(value, (list, tuple)):
        return [safe_json_value(item, limit) for item in value[:50]]
    if isinstance(value, dict):
        return {safe_text(k, 200) or "": safe_json_value(v, limit) for k, v in list(value.items())[:100]}
    return safe_text(value, limit)


def job_status(job: Any) -> str:
    try:
        status = job.get_status(refresh=False)
        return getattr(status, "value", str(status))
    except Exception:
        return "unknown"


def classify_error(exc_info: str | None) -> dict[str, str | None]:
    if not exc_info:
        return {"type": None, "label": None, "message": None}
    text = exc_info.lower()
    if "timeout" in text or "timed out" in text:
        kind, label = "timeout", "タイムアウト"
    elif "connection refused" in text:
        kind, label = "connection_refused", "接続拒否"
    elif "model" in text and ("not found" in text or "pull" in text):
        kind, label = "model_not_found", "モデル未検出"
    elif "json" in text:
        kind, label = "invalid_json", "JSONエラー"
    elif "ollama" in text:
        kind, label = "ollama_error", "Ollamaエラー"
    else:
        kind, label = "error", "エラー"
    return {"type": kind, "label": label, "message": safe_text(exc_info, 500)}


def task_from_job(job: Any) -> dict[str, Any]:
    func_name = getattr(job, "func_name", None)
    args = getattr(job, "args", ()) or ()
    kwargs = getattr(job, "kwargs", {}) or {}
    meta = getattr(job, "meta", {}) or {}

    model = meta.get("model") or kwargs.get("model")
    project = meta.get("project") or kwargs.get("project")
    kind = meta.get("kind") or kwargs.get("kind")
    resource = meta.get("resource") or kwargs.get("resource")
    resource_key = meta.get("resource_key") or kwargs.get("resource_key")
    ollama_host = meta.get("ollama_host") or kwargs.get("ollama_host")
    ollama_endpoint = meta.get("ollama_endpoint") or kwargs.get("ollama_endpoint")
    ollama_model = meta.get("ollama_model") or meta.get("model") or kwargs.get("ollama_model") or kwargs.get("model")
    source = meta.get("source") or kwargs.get("source")
    queue_class = meta.get("queue_class") or kwargs.get("queue_class")
    priority_class = meta.get("priority_class") or kwargs.get("priority_class")

    for value in args:
        if not model and isinstance(value, str) and (":" in value and len(value) < 80):
            model = value
        if not kind and isinstance(value, str) and value.startswith(("http://", "https://")):
            kind = "http"

    return {
        "name": func_name,
        "project": project,
        "kind": kind,
        "model": model,
        "resource": resource,
        "resource_key": resource_key,
        "ollama_host": ollama_host,
        "ollama_endpoint": ollama_endpoint,
        "ollama_model": ollama_model,
        "source": source,
        "queue_class": queue_class,
        "priority_class": priority_class,
    }


def job_preview(job: Any) -> dict[str, Any]:
    args = getattr(job, "args", ()) or ()
    kwargs = getattr(job, "kwargs", {}) or {}
    result = getattr(job, "result", None)
    exc_info = getattr(job, "exc_info", None)

    prompt = None
    for key in ("prompt", "input", "text", "url"):
        if key in kwargs:
            prompt = kwargs[key]
            break
    if prompt is None and args:
        prompt = args[-1] if len(args) <= 3 else args[:3]

    return {
        "input_preview": safe_text(prompt),
        "output_preview": safe_text(result),
        "error": classify_error(exc_info),
    }


def serialize_job(job: Any, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": job.id,
        "queue": getattr(job, "origin", None),
        "status": job_status(job),
        "task": task_from_job(job),
        "created_at": iso(getattr(job, "created_at", None)),
        "enqueued_at": iso(getattr(job, "enqueued_at", None)),
        "started_at": iso(getattr(job, "started_at", None)),
        "ended_at": iso(getattr(job, "ended_at", None)),
        "timeout": safe_text(getattr(job, "timeout", None), 100),
        "ttl": getattr(job, "ttl", None),
        "result_ttl": getattr(job, "result_ttl", None),
        "failure_ttl": getattr(job, "failure_ttl", None),
        "worker_name": getattr(job, "worker_name", None),
        "description": safe_text(getattr(job, "description", None), 500),
        "actions": ["detail"],
    }
    status = data["status"]
    if status in ("failed", "finished", "deferred", "queued", "scheduled", "canceled", "stopped"):
        data["actions"].append("delete")
    if status == "failed":
        data["actions"].append("requeue")
    data.update(job_preview(job))
    if detail:
        data["args"] = safe_json_value(getattr(job, "args", ()))
        data["kwargs"] = safe_json_value(getattr(job, "kwargs", {}))
        data["meta"] = safe_json_value(getattr(job, "meta", {}))
        data["result"] = safe_json_value(getattr(job, "result", None))
        data["exc_info"] = safe_text(getattr(job, "exc_info", None), MAX_FULL_TEXT)
    return data
