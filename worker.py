"""
RQ worker process.

Run this as a separate, long-lived process alongside the Flask API when
REDIS_URL is configured — it's what actually executes the investigation
pipeline jobs enqueued by `services.task_queue.RQTaskQueue`.

    python worker.py

In production (see render.yaml), this runs as its own service/dyno so it
scales independently of the API and survives API restarts/deploys.
"""
from __future__ import annotations

import logging
import sys

from config import config

logging.basicConfig(level=logging.INFO if not config.DEBUG else logging.DEBUG)
logger = logging.getLogger(__name__)


def main() -> None:
    if not config.REDIS_URL:
        logger.error(
            "REDIS_URL is not set — there is nothing for this worker to consume. "
            "Set REDIS_URL and enqueue investigations via services.task_queue.RQTaskQueue first."
        )
        sys.exit(1)

    import redis
    from rq import Worker, Queue

    conn = redis.from_url(config.REDIS_URL)
    queue = Queue("investigations", connection=conn)

    logger.info("Starting RQ worker, listening on queue 'investigations' at %s", config.REDIS_URL)
    worker = Worker([queue], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
