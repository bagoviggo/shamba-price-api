import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import AsyncSessionLocal
from app.services.scraper import run_scrape

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")


async def _run_daily_scrape() -> None:
    logger.info("⏰ Scheduled daily scrape starting...")
    async with AsyncSessionLocal() as session:
        result = await run_scrape(session)
    logger.info("📦 Daily scrape result: %s", result)


def start_scheduler() -> None:
    scheduler.add_job(
        _run_daily_scrape,
        CronTrigger(hour=6, minute=0),   # 06:00 Africa/Nairobi (EAT)
        id="daily_kamis_scrape",
        replace_existing=True,
        misfire_grace_time=600,          # run even if missed by up to 10 min
    )
    scheduler.start()
    logger.info("📅 Scheduler started — daily scrape at 06:00 EAT")
