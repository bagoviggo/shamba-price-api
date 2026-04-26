import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cache import get_cached, set_cached
from app.config import get_settings

logger   = logging.getLogger(__name__)
router   = APIRouter()
settings = get_settings()


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """
    Dashboard summary:
      - latest scrape date
      - total records in DB
      - county + commodity counts
      - top 5 price movers (for AI context injection)
      - last scrape run info
    """
    cache_key = "shamba:stats:summary"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    # DB overview
    overview = await db.execute(text("""
        SELECT
            MAX(recorded_date)        AS latest_date,
            COUNT(*)                  AS total_records,
            COUNT(DISTINCT county)    AS county_count,
            COUNT(DISTINCT commodity) AS commodity_count
        FROM price_records
    """))
    ov = dict(overview.mappings().first() or {})

    # Top movers (biggest % change today vs yesterday)
    movers = await db.execute(text("""
        WITH today AS (
            SELECT commodity, county, market, retail_price, price_unit
            FROM price_records
            WHERE recorded_date = (SELECT MAX(recorded_date) FROM price_records)
              AND retail_price IS NOT NULL
        ),
        yesterday AS (
            SELECT commodity, county, market, retail_price
            FROM price_records
            WHERE recorded_date = (
                SELECT MAX(recorded_date) FROM price_records
                WHERE recorded_date < (SELECT MAX(recorded_date) FROM price_records)
            )
            AND retail_price IS NOT NULL
        )
        SELECT
            t.commodity, t.county, t.market,
            t.retail_price, t.price_unit,
            ROUND(((t.retail_price - y.retail_price) / y.retail_price * 100)::numeric, 1) AS change_pct
        FROM today t
        JOIN yesterday y ON t.commodity = y.commodity AND t.county = y.county AND t.market = y.market
        WHERE y.retail_price > 0
        ORDER BY ABS((t.retail_price - y.retail_price) / y.retail_price) DESC
        LIMIT 5
    """))
    top_movers = [dict(r) for r in movers.mappings().all()]

    # Last scrape run
    last_run = await db.execute(text("""
        SELECT run_at, status, records_inserted, records_skipped, duration_seconds
        FROM scrape_runs
        ORDER BY run_at DESC
        LIMIT 1
    """))
    last_run_row = last_run.mappings().first()

    response = {
        **ov,
        "top_movers": top_movers,
        "last_scrape": dict(last_run_row) if last_run_row else None,
    }
    # Serialise dates/decimals
    for k, v in response.items():
        if hasattr(v, "isoformat"):
            response[k] = v.isoformat()

    await set_cached(cache_key, response, ttl=settings.cache_ttl_summary)
    return response
