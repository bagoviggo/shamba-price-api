import logging
from typing import Optional
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
async def list_counties(db: AsyncSession = Depends(get_db)):
    """All counties with market count and last update date."""
    cache_key = "shamba:counties:all"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    q = text("""
        SELECT
            county,
            COUNT(DISTINCT market)    AS market_count,
            COUNT(DISTINCT commodity) AS commodity_count,
            MAX(recorded_date)        AS latest_date
        FROM price_records
        GROUP BY county
        ORDER BY county
    """)
    result = await db.execute(q)
    rows   = result.mappings().all()

    response = [dict(r) for r in rows]
    await set_cached(cache_key, response, ttl=settings.cache_ttl_static)
    return response


@router.get("/{name}/prices")
async def get_county_prices(
    name     : str,
    commodity: Optional[str] = Query(None),
    db       : AsyncSession  = Depends(get_db),
):
    """All latest prices in a county, optionally filtered by commodity."""
    cache_key = _make_key("county_prices", {"name": name, "commodity": commodity})
    cached = await get_cached(cache_key)
    if cached:
        return cached

    filters = "AND commodity ILIKE :commodity" if commodity else ""
    q = text(f"""
        SELECT
            commodity, classification, market,
            retail_price, wholesale_price, price_unit, supply_volume, recorded_date
        FROM price_records
        WHERE county ILIKE :county
          AND recorded_date = (
              SELECT MAX(recorded_date) FROM price_records WHERE county ILIKE :county
          )
          {filters}
        ORDER BY commodity, market
    """)
    params: dict = {"county": f"%{name}%"}
    if commodity:
        params["commodity"] = f"%{commodity}%"

    result = await db.execute(q, params)
    rows   = result.mappings().all()

    response = {"county": name, "count": len(rows), "data": [dict(r) for r in rows]}
    await set_cached(cache_key, response, ttl=settings.cache_ttl_daily)
    return response


@router.get("/{name}/markets")
async def get_county_markets(name: str, db: AsyncSession = Depends(get_db)):
    """All markets in a county with their latest commodity counts."""
    q = text("""
        SELECT market, COUNT(DISTINCT commodity) AS commodity_count, MAX(recorded_date) AS latest_date
        FROM price_records
        WHERE county ILIKE :county
        GROUP BY market
        ORDER BY market
    """)
    result = await db.execute(q, {"county": f"%{name}%"})
    rows   = result.mappings().all()
    return {"county": name, "markets": [dict(r) for r in rows]}
