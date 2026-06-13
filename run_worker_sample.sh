#!/bin/sh
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
exec env \
  PYTHONPATH="$PWD" \
  RQDB4AI_REDIS_URL="${RQDB4AI_REDIS_URL:-redis://127.0.0.1:6379/0}" \
  ${RQDB4AI_RQ_BIN:-rq} worker rqdb4ai-sample --url "${RQDB4AI_REDIS_URL:-redis://127.0.0.1:6379/0}"
