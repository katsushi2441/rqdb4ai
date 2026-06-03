# Kurage RQ Dashboard for AI

`rqdb4ai` is a generic RQ/Redis job management API and dashboard for humans and AI agents.

It is designed to be independent from any specific application. Application repositories provide their own job modules and enqueue scripts.

## API

- `GET /healthz`
- `GET /api/capabilities`
- `GET /api/summary`
- `GET /api/queues`
- `GET /api/workers`
- `GET /api/jobs?queue=&status=&limit=&offset=`
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/logs`
- `POST /api/jobs/{id}/requeue`
- `POST /api/jobs/{id}/cancel`
- `DELETE /api/jobs/{id}`
- `POST /api/enqueue`
- `POST /api/sample/enqueue`
- `POST /api/bulk/requeue`

## Web UI

The PHP dashboard lives in the generic project web folder:

```text
web/rqdb4ai.php
web/config.sample.php
```

`web/config.php` is deployment-specific and is intentionally ignored by Git. Copy `web/config.sample.php` to `web/config.php` on the deployment target and set real values there.

Deploy the current web files:

```bash
cd /home/kojima/work/rqdb4ai
RQDB4AI_FTP_REMOTE_DIR=web/<public-site-folder> python3 scripts/deploy_web.py
```

## Resource Queues

Application workers can use resource-aware queue names. For example, jobs that use the same Ollama host can share a host-specific queue, while web-triggered jobs and background worker jobs can use separate priority classes.

Example queue names:

```text
ollama-192-168-0-14-web
ollama-192-168-0-14-worker
```

`queue=auto` lets the API choose the queue from job metadata. For Ollama jobs, the API uses `ollama_host` plus the normalized source class:

```text
source=web_online  -> queue_class=web    -> ollama-<host>-web
source=worker_auto -> queue_class=worker -> ollama-<host>-worker
```


## Auth

Use bearer tokens. Roles are ordered as `read < operate < admin`.

```bash
export RQDB4AI_READ_TOKEN=read-token
export RQDB4AI_OPERATE_TOKEN=operate-token
export RQDB4AI_ADMIN_TOKEN=admin-token
```

For simple development:

```bash
export RQDB4AI_API_TOKEN=dev-token
export RQDB4AI_API_TOKEN_ROLE=admin
```

## Run

```bash
cd /home/kojima/work/rqdb4ai
python3 -m pip install -r requirements.txt
RQDB4AI_API_TOKEN=dev-token python3 -m uvicorn server:app --host 127.0.0.1 --port 18300
```

Expose the API through nginx over HTTPS when the PHP UI runs on another server.

## Worker

```bash
cd /home/kojima/work/rqdb4ai
python3 -m rq worker rqdb4ai-sample --url redis://127.0.0.1:6379/0
```

Application-specific worker scripts should live in the application repository, not in `rqdb4ai`.
