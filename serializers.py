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


def error_summary(exc_info: str | None) -> str | None:
    if not exc_info:
        return None
    lines = [line.strip() for line in exc_info.splitlines() if line.strip()]
    if not lines:
        return None
    for line in reversed(lines):
        if line.startswith(("File ", "Traceback ")):
            continue
        if ":" in line:
            return safe_text(line, 500)
    return safe_text(lines[-1], 500)


def job_status(job: Any) -> str:
    try:
        status = job.get_status(refresh=False)
        return getattr(status, "value", str(status))
    except Exception:
        return "unknown"


def classify_error(exc_info: str | None) -> dict[str, str | None]:
    if not exc_info:
        return {"type": None, "label": None, "message": None, "summary": None}
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
    summary = error_summary(exc_info)
    return {"type": kind, "label": label, "message": summary or safe_text(exc_info, 500), "summary": summary}


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


def job_preview(job: Any, rq_status: str | None = None) -> dict[str, Any]:
    args = getattr(job, "args", ()) or ()
    kwargs = getattr(job, "kwargs", {}) or {}
    result = getattr(job, "result", None)
    exc_info = getattr(job, "exc_info", None) if rq_status in {"failed", "stopped", "canceled"} else None

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


def job_lifecycle(job: Any, rq_status: str) -> dict[str, Any]:
    """Describe what the RQ job result actually means.

    RQ's "finished" only means the Python callable returned. It does not always
    mean the external/business task is complete.
    """
    result = getattr(job, "result", None)
    if rq_status == "failed":
        return {
            "state": "failed",
            "label": "失敗",
            "scope": "rq_job",
            "terminal": True,
            "rq_status": rq_status,
            "items": 0,
            "note": "RQジョブが失敗しました",
        }
    if rq_status == "started":
        return {
            "state": "running",
            "label": "実行中",
            "scope": "rq_job",
            "terminal": False,
            "rq_status": rq_status,
            "items": 0,
            "note": "RQジョブを実行中です",
        }
    if rq_status in ("queued", "scheduled", "deferred"):
        return {
            "state": rq_status,
            "label": {"queued": "待機", "scheduled": "予定", "deferred": "保留"}.get(rq_status, rq_status),
            "scope": "rq_job",
            "terminal": False,
            "rq_status": rq_status,
            "items": 0,
            "note": "RQジョブはまだ完了していません",
        }
    if rq_status in ("stopped", "canceled"):
        return {
            "state": rq_status,
            "label": {"stopped": "停止", "canceled": "取消"}.get(rq_status, rq_status),
            "scope": "rq_job",
            "terminal": True,
            "rq_status": rq_status,
            "items": 0,
            "note": "RQジョブは完了していません",
        }

    if rq_status == "finished" and isinstance(result, dict):
        scope = str(result.get("completion_scope") or result.get("scope") or "").strip().lower()
        status = str(result.get("status") or "").strip().lower()
        trigger_started = bool(result.get("trigger_started"))
        business_terminal = result.get("business_terminal")
        items = result.get("items", 0)
        note = safe_text(result.get("note"), 500)
        if scope == "trigger" or business_terminal is False:
            return {
                "state": "triggered",
                "label": "起動済み",
                "scope": "external_trigger",
                "terminal": False,
                "rq_status": rq_status,
                "items": int(items or 0) if isinstance(items, (int, float, str)) and str(items).isdigit() else 0,
                "note": note or "外部処理を起動しました。外部処理の完了ではありません",
            }
        if status in {"warn", "warning"}:
            return {
                "state": "warning",
                "label": "警告",
                "scope": "business_result",
                "terminal": True,
                "rq_status": rq_status,
                "items": int(items or 0) if isinstance(items, (int, float, str)) and str(items).isdigit() else 0,
                "note": note,
            }
        if status in {"failed", "error", "down"}:
            return {
                "state": "failed",
                "label": "失敗",
                "scope": "business_result",
                "terminal": True,
                "rq_status": rq_status,
                "items": int(items or 0) if isinstance(items, (int, float, str)) and str(items).isdigit() else 0,
                "note": note,
            }
        return {
            "state": "complete",
            "label": "完了",
            "scope": "business_result",
            "terminal": True,
            "rq_status": rq_status,
            "items": int(items or 0) if isinstance(items, (int, float, str)) and str(items).isdigit() else 0,
            "note": note,
        }

    if rq_status == "finished":
        return {
            "state": "complete",
            "label": "完了",
            "scope": "rq_job",
            "terminal": True,
            "rq_status": rq_status,
            "items": 0,
            "note": "RQジョブが完了しました",
        }

    return {
        "state": rq_status,
        "label": rq_status,
        "scope": "rq_job",
        "terminal": False,
        "rq_status": rq_status,
        "items": 0,
        "note": "",
    }


def serialize_job(job: Any, detail: bool = False) -> dict[str, Any]:
    status = job_status(job)
    lifecycle = job_lifecycle(job, status)
    data = {
        "id": job.id,
        "queue": getattr(job, "origin", None),
        "status": status,
        "status_label": lifecycle["label"],
        "lifecycle": lifecycle,
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
    if status in ("failed", "finished", "deferred", "queued", "scheduled", "canceled", "stopped"):
        data["actions"].append("delete")
    if status == "failed":
        data["actions"].append("requeue")
    data.update(job_preview(job, status))
    if detail:
        data["args"] = safe_json_value(getattr(job, "args", ()))
        data["kwargs"] = safe_json_value(getattr(job, "kwargs", {}))
        data["meta"] = safe_json_value(getattr(job, "meta", {}))
        data["result"] = safe_json_value(getattr(job, "result", None))
        data["exc_info"] = safe_text(getattr(job, "exc_info", None), MAX_FULL_TEXT)
    return data
