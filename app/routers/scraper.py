import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import text, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.scraper import run_scrape
from app.models import ScrapeRun

logger = logging.getLogger(__name__)
router = APIRouter()

# Simple in-memory flag so we don't fire two scrapes at once
_scrape_running = False


@router.post("/run")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a full KAMIS scrape.
    Runs in the background so the HTTP request returns immediately.
    """
    global _scrape_running
    if _scrape_running:
        return {"status": "already_running", "message": "A scrape is already in progress"}

    async def _do_scrape():
        global _scrape_running
        _scrape_running = True
        try:
            async with __import__("app.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as session:
                result = await run_scrape(session)
            logger.info("Manual scrape finished: %s", result)
        finally:
            _scrape_running = False

    background_tasks.add_task(_do_scrape)
    return {"status": "started", "message": "Scrape started in background. Check /scraper/status for updates."}


@router.get("/status")
async def scrape_status(db: AsyncSession = Depends(get_db)):
    """Last 10 scrape run records."""
    global _scrape_running

    q    = select(ScrapeRun).order_by(desc(ScrapeRun.run_at)).limit(10)
    rows = (await db.execute(q)).scalars().all()

    return {
        "currently_running": _scrape_running,
        "recent_runs": [r.to_dict() for r in rows],
    }
