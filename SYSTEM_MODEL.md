# RQDB4AI System Model

RQDB4AI is a generic RQ/Redis queue management system. It must not depend on any specific application.

## Inputs

RQDB4AI reads only these generic inputs:

- Redis/RQ queues
- Redis/RQ job registries
- Redis/RQ workers
- Job metadata supplied at enqueue time
- Optional configured execution queue names from `RQDB4AI_QUEUES`

Application-specific code, database access, and business rules belong in each application repository.

## Outputs

The dashboard and API expose four separate outputs.

### Execution Queues

`execution_queues` are the queues RQDB4AI considers active execution targets.

They show live queue state:

- `queued`
- `started`
- `deferred`
- `scheduled`

They are not the source of truth for completed job history.

### Job History Queues

`history_queues` are queues that currently have RQ job registry history.

They show registry history:

- `queued`
- `started`
- `finished`
- `failed`
- `stopped`
- `canceled`
- `deferred`
- `scheduled`

If a completed job exists in job history, the corresponding history queue must show that completed count.

### Workers

`workers` are RQ worker processes.

They show:

- worker name
- state
- watched queues
- current job id
- heartbeat

Worker state is not job result state.

### Jobs

`jobs` are individual RQ jobs.

They show:

- job id
- queue
- status
- function name
- generic metadata
- timestamps
- result or error

The job list and history queue counts must use the same RQ registries.

## Routing

`auto` is an enqueue-time routing directive only.

It must be resolved before enqueueing:

- resource-specific jobs route to the matching configured resource queue
- web/manual jobs route to a configured `*-web` execution queue
- worker/cron jobs route to a configured `*-worker` execution queue

`auto` must not remain as a physical Redis/RQ queue.

## Rules

- Do not hide queues to make the UI look clean.
- Do not merge live queue counts and completed history counts.
- Do not treat enqueue success as external task success.
- Do not put application-specific job modules in this repository.
- Do not put application-specific names in RQDB4AI documents or code unless they are user-provided runtime metadata from Redis/RQ.
