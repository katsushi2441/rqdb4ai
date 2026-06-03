#!/bin/sh
cd /home/kojima/work/rqdb4ai || exit 1
exec env \
  PYTHONPATH=/home/kojima/work/rqdb4ai \
  RQDB4AI_REDIS_URL="${RQDB4AI_REDIS_URL:-redis://127.0.0.1:6379/0}" \
  /home/kojima/.local/bin/rq worker rqdb4ai-sample --url "${RQDB4AI_REDIS_URL:-redis://127.0.0.1:6379/0}"
