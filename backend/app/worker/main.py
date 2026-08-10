import asyncio
import logging

from app.core.logging import setup_logging
from app.core.redis import create_redis_client

logger = logging.getLogger("lumio.worker")

# Placeholder per la milestone 01 — Foundation: dimostra solo che il servizio worker
# si avvia e raggiunge Redis. La libreria di job queue (arq/Celery/RQ) e i job reali
# (parsing PDF, OCR, classificazione, ecc.) arrivano dalla milestone 04 — Import Engine.


async def main() -> None:
    setup_logging()
    redis_client = create_redis_client()

    await redis_client.ping()
    logger.info("worker up, redis reachable")

    while True:
        await asyncio.sleep(30)
        logger.info("worker alive")


if __name__ == "__main__":
    asyncio.run(main())
