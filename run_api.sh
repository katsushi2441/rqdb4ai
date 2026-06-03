#!/bin/sh
cd /home/kojima/work/rqdb4ai || exit 1
exec env \
  RQDB4AI_API_TOKEN="${RQDB4AI_API_TOKEN:?RQDB4AI_API_TOKEN required}" \
  RQDB4AI_API_TOKEN_ROLE="${RQDB4AI_API_TOKEN_ROLE:-admin}" \
  RQDB4AI_QUEUES="${RQDB4AI_QUEUES:-rqdb4ai-sample}" \
  RQDB4AI_REDIS_URL="${RQDB4AI_REDIS_URL:-redis://127.0.0.1:6379/0}" \
  python3 -m uvicorn server:app --host 0.0.0.0 --port 18300
