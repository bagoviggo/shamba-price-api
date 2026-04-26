import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cache import get_cached, set_cached, _make_key
from app.config import get_settings

logger   = logging.getLogger(__name__)
router   = APIRouter()
settings = get_settings()


@router.get("")
async def list_commodities(db: AsyncSession = Depends(get_db)):
    """All commodities tracked in the DB, with latest avg price and market coverage."""
    cache_key = "shamba:commodities:all"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    q = text("""
        SELECT
            commodity,
            MAX(recorded_date)                      AS latest_date,
            ROUND(AVG(retail_price)::numeric,    2) AS avg_retail,
            ROUND(AVG(wholesale_price)::numeric, 2) AS avg_wholesale,
            COUNT(DISTINCT market)                  AS market_count,
            COUNT(DISTINCT county)                  AS county_count
        FROM price_records
        GROUP BY commodity
        ORDER BY commodity
    """)
    result = await db.execute(q)
    rows   = result.mappings().all()

    response = [dict(r) for r in rows]
    await set_cached(cache_key, response, ttl=settings.cache_ttl_static)
    return response


@router.get("/{name}")
async def get_commodity(name: str, db: AsyncSession = Depends(get_db)):
    """Summary stats + latest prices for a single commodity."""
    cache_key = _make_key("commodity_detail", {"name": name})
    cached = await get_cached(cache_key)
    if cached:
        return cached

    summary_q = text("""
        SELECT
            commodity,
            MAX(recorded_date)                          AS latest_date,
            ROUND(AVG(retail_price)::numeric,    2)     AS avg_retail,
            ROUND(AVG(wholesale_price)::numeric, 2)     AS avg_wholesale,
            MIN(retail_price)                           AS min_retail,
            MAX(retail_price)                           AS max_retail,
            COUNT(DISTINCT market)                      AS market_count,
            COUNT(DISTINCT county)                      AS county_count
        FROM price_records
        WHERE commodity ILIKE :name
        GROUP BY commodity
        LIMIT 1
    """)
    summary_result = await db.execute(summary_q, {"name": f"%{name}%"})
    summary = summary_result.mappings().first()
    if not summary:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Commodity '{name}' not found")

    latest_q = text("""
        SELECT market, county, retail_price, wholesale_price, price_unit, supply_volume, recorded_date
        FROM price_records
        WHERE commodity ILIKE :name
          AND recorded_date = (SELECT MAX(recorded_date) FROM price_records WHERE commodity ILIKE :name)
        ORDER BY retail_price DESC NULLS LAST
    """)
    latest_result = await db.execute(latest_q, {"name": f"%{name}%"})
    latest_rows   = latest_result.mappings().all()

    response = {
        "summary": dict(summary),
        "latest_prices": [dict(r) for r in latest_rows],
    }
    await set_cached(cache_key, response, ttl=settings.cache_ttl_trend)
    return response
