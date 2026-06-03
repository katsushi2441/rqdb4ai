#!/usr/bin/env python3
from rq_client import get_queue


def main() -> None:
    queue = get_queue("rqdb4ai-sample")
    job = queue.enqueue(
        "sample_jobs.echo_job",
        message="hello from rqdb4ai sample",
        meta={"project": "rqdb4ai", "kind": "sample"},
        result_ttl=86400,
        failure_ttl=604800,
    )
    print(job.id)


if __name__ == "__main__":
    main()
