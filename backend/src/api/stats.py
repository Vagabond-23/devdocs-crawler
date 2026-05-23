"""Stats and metrics API — observability endpoints."""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
import asyncio
from sqlalchemy import select

from src.dependencies import get_redis
from src.db.session import async_session_factory
from src.models import CrawlJob

router = APIRouter()

@router.websocket("/stats/live")
async def stats_live(websocket: WebSocket, redis: aioredis.Redis = Depends(get_redis)):
    """
    WebSocket endpoint that pushes live statistics to the client every second.
    Also sends the status of the most recent crawl job.
    """
    await websocket.accept()
    try:
        while True:
            # Get crawler metrics
            stats = await get_stats(redis)

            # Get latest job status
            job_status = "none"
            async with async_session_factory() as db:
                result = await db.execute(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(1))
                latest_job = result.scalar_one_or_none()
                if latest_job:
                    job_status = latest_job.status.value

            await websocket.send_json({
                "stats": stats,
                "job_status": job_status
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        # Client disconnected normally
        pass
    except Exception as e:
        # Avoid crashing the router on unexpected connection drops
        print(f"WebSocket error: {e}")

@router.get("/stats")
async def get_stats(
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    Return real-time crawler statistics as JSON.

    Reads counters from Redis that are updated by the crawler workers.
    """
    pipe = redis.pipeline()
    pipe.get("metrics:pages_fetched")
    pipe.get("metrics:pages_failed")
    pipe.get("metrics:pages_304")
    pipe.get("metrics:pages_duplicate")
    pipe.get("metrics:pages_indexed")
    pipe.scard("seen_urls")
    pipe.scard("frontier:hosts")
    pipe.get("metrics:active_workers")
    results = await pipe.execute()

    return {
        "pages_fetched": int(results[0] or 0),
        "pages_failed": int(results[1] or 0),
        "pages_not_modified": int(results[2] or 0),
        "pages_duplicate": int(results[3] or 0),
        "pages_indexed": int(results[4] or 0),
        "urls_discovered": int(results[5] or 0),
        "active_hosts": int(results[6] or 0),
        "active_workers": int(results[7] or 0),
    }


@router.get("/metrics")
async def get_metrics(
    redis: aioredis.Redis = Depends(get_redis),
) -> str:
    """
    Return metrics in Prometheus exposition format.

    Can be scraped by Prometheus or any compatible monitoring system.
    """
    stats = await get_stats(redis)

    lines = [
        "# HELP crawler_pages_fetched_total Total pages successfully fetched",
        "# TYPE crawler_pages_fetched_total counter",
        f'crawler_pages_fetched_total {stats["pages_fetched"]}',
        "",
        "# HELP crawler_pages_failed_total Total pages that failed to fetch",
        "# TYPE crawler_pages_failed_total counter",
        f'crawler_pages_failed_total {stats["pages_failed"]}',
        "",
        "# HELP crawler_pages_not_modified_total Pages skipped (304 Not Modified)",
        "# TYPE crawler_pages_not_modified_total counter",
        f'crawler_pages_not_modified_total {stats["pages_not_modified"]}',
        "",
        "# HELP crawler_pages_duplicate_total Pages skipped (duplicate content)",
        "# TYPE crawler_pages_duplicate_total counter",
        f'crawler_pages_duplicate_total {stats["pages_duplicate"]}',
        "",
        "# HELP crawler_pages_indexed_total Pages indexed in Meilisearch",
        "# TYPE crawler_pages_indexed_total counter",
        f'crawler_pages_indexed_total {stats["pages_indexed"]}',
        "",
        "# HELP crawler_urls_discovered Total unique URLs discovered",
        "# TYPE crawler_urls_discovered gauge",
        f'crawler_urls_discovered {stats["urls_discovered"]}',
        "",
        "# HELP crawler_active_hosts Number of hosts with queued URLs",
        "# TYPE crawler_active_hosts gauge",
        f'crawler_active_hosts {stats["active_hosts"]}',
        "",
        "# HELP crawler_active_workers Currently active fetch workers",
        "# TYPE crawler_active_workers gauge",
        f'crawler_active_workers {stats["active_workers"]}',
    ]
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n")
