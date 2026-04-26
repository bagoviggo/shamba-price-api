import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_, func, text, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import PriceRecord
from app.schemas import PriceListResponse
from app.services.cache import get_cached, set_cached, _make_key
from app.config import get_settings

logger   = logging.getLogger(__name__)
router   = APIRouter()
settings = get_settings()


def _row_to_dict(r: PriceRecord) -> dict:
    return {
        "id":              r.id,
        "commodity":       r.commodity,
        "classification":  r.classification,
        "grade":           r.grade,
        "market":          r.market,
        "county":          r.county,
        "wholesale_price": float(r.wholesale_price) if r.wholesale_price else None,
        "retail_price":    float(r.retail_price)    if r.retail_price    else None,
        "price_unit":      r.price_unit,
        "supply_volume":   float(r.supply_volume)   if r.supply_volume   else None,
        "recorded_date":   r.recorded_date.isoformat() if r.recorded_date else None,
    }


# ── GET / ─────────────────────────────────────────────────────────────────────

@router.get("")
async def get_prices(
    commodity : Optional[str]  = Query(None),
    county    : Optional[str]  = Query(None),
    market    : Optional[str]  = Query(None),
    date_from : Optional[date] = Query(None),
    date_to   : Optional[date] = Query(None),
    page      : int            = Query(1,  ge=1),
    limit     : int            = Query(50, le=500),
    db        : AsyncSession   = Depends(get_db),
):
    cache_key = _make_key("prices", {
        "commodity": commodity, "county": county, "market": market,
        "date_from": str(date_from), "date_to": str(date_to),
        "page": page, "limit": limit,
    })
    cached = await get_cached(cache_key)
    if cached:
        return cached

    filters = []
    if commodity : filters.append(PriceRecord.commodity.ilike(f"%{commodity}%"))
    if county    : filters.append(PriceRecord.county.ilike(f"%{county}%"))
    if market    : filters.append(PriceRecord.market.ilike(f"%{market}%"))
    if date_from : filters.append(PriceRecord.recorded_date >= date_from)
    if date_to   : filters.append(PriceRecord.recorded_date <= date_to)

    count_q = select(func.count()).select_from(PriceRecord)
    if filters:
        count_q = count_q.where(and_(*filters))
    total = (await db.execute(count_q)).scalar_one()

    data_q = select(PriceRecord).order_by(desc(PriceRecord.recorded_date))
    if filters:
        data_q = data_q.where(and_(*filters))
    data_q = data_q.offset((page - 1) * limit).limit(limit)

    rows = (await db.execute(data_q)).scalars().all()
    response = {"total": total, "page": page, "limit": limit,
                "data": [_row_to_dict(r) for r in rows]}
    await set_cached(cache_key, response, ttl=3600)
    return response


# ── GET /daily ────────────────────────────────────────────────────────────────

@router.get("/daily")
async def get_daily_prices(
    county   : Optional[str] = Query(None),
    commodity: Optional[str] = Query(None),
    db       : AsyncSession  = Depends(get_db),
):
    cache_key = _make_key("daily", {"county": county, "commodity": commodity})
    cached = await get_cached(cache_key)
    if cached:
        return cached

    latest_result = await db.execute(text("SELECT MAX(recorded_date) FROM price_records"))
    latest_date   = latest_result.scalar()
    if not latest_date:
        return {"date": None, "data": []}

    filters = [PriceRecord.recorded_date == latest_date]
    if county    : filters.append(PriceRecord.county.ilike(f"%{county}%"))
    if commodity : filters.append(PriceRecord.commodity.ilike(f"%{commodity}%"))

    q    = select(PriceRecord).where(and_(*filters)).order_by(PriceRecord.commodity)
    rows = (await db.execute(q)).scalars().all()

    response = {"date": latest_date.isoformat(), "count": len(rows),
                "data": [_row_to_dict(r) for r in rows]}
    await set_cached(cache_key, response, ttl=settings.cache_ttl_daily)
    return response


# ── GET /commodity/{name}/trend ───────────────────────────────────────────────

@router.get("/commodity/{name}/trend")
async def get_commodity_trend(
    name: str,
    days: int          = Query(30, ge=7, le=180),
    db  : AsyncSession = Depends(get_db),
):
    cache_key = _make_key("trend", {"name": name, "days": days})
    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Use interval arithmetic instead of CURRENT_DATE - :days (asyncpg compat)
    q = text("""
        SELECT
            recorded_date,
            county,
            ROUND(CAST(AVG(retail_price)    AS numeric), 2) AS avg_retail,
            ROUND(CAST(AVG(wholesale_price) AS numeric), 2) AS avg_wholesale,
            ROUND(CAST(SUM(supply_volume)   AS numeric), 0) AS total_supply,
            COUNT(*) AS data_points
        FROM price_records
        WHERE commodity ILIKE :name
          AND recorded_date >= CURRENT_DATE - CAST(:days AS INTEGER)
        GROUP BY recorded_date, county
        ORDER BY recorded_date ASC, county
    """)
    result = await db.execute(q, {"name": f"%{name}%", "days": days})
    rows   = result.mappings().all()

    response = [dict(r) for r in rows]
    await set_cached(cache_key, response, ttl=settings.cache_ttl_trend)
    return response


# ── GET /compare ──────────────────────────────────────────────────────────────

@router.get("/compare")
async def compare_counties(
    commodity: str          = Query(...),
    counties : str          = Query(..., description="Comma-separated county names"),
    days     : int          = Query(7, ge=1, le=30),
    db       : AsyncSession = Depends(get_db),
):
    county_list = [c.strip() for c in counties.split(",") if c.strip()]
    if not county_list:
        raise HTTPException(status_code=400, detail="Provide at least one county")

    cache_key = _make_key("compare", {
        "commodity": commodity, "counties": sorted(county_list), "days": days
    })
    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Build IN clause manually to avoid asyncpg array binding issues
    placeholders = ", ".join(f":county_{i}" for i in range(len(county_list)))
    county_params = {f"county_{i}": c for i, c in enumerate(county_list)}

    q = text(f"""
        SELECT
            county,
            ROUND(CAST(AVG(retail_price)    AS numeric), 2) AS avg_retail,
            ROUND(CAST(AVG(wholesale_price) AS numeric), 2) AS avg_wholesale,
            MAX(recorded_date)                              AS latest_date,
            COUNT(DISTINCT market)                          AS market_count
        FROM price_records
        WHERE commodity ILIKE :commodity
          AND county IN ({placeholders})
          AND recorded_date >= CURRENT_DATE - CAST(:days AS INTEGER)
        GROUP BY county
        ORDER BY avg_retail DESC NULLS LAST
    """)
    result = await db.execute(q, {
        "commodity": f"%{commodity}%", "days": days, **county_params
    })
    rows = result.mappings().all()

    response = [dict(r) for r in rows]
    await set_cached(cache_key, response, ttl=settings.cache_ttl_compare)
    return response


# ── GET /movers ───────────────────────────────────────────────────────────────

@router.get("/movers")
async def get_top_movers(
    limit: int          = Query(10, ge=1, le=50),
    db   : AsyncSession = Depends(get_db),
):
    cache_key = _make_key("movers", {"limit": limit})
    cached = await get_cached(cache_key)
    if cached:
        return cached

    q = text("""
        WITH latest_two_dates AS (
            SELECT DISTINCT recorded_date
            FROM price_records
            ORDER BY recorded_date DESC
            LIMIT 2
        ),
        today AS (
            SELECT commodity, county, market, retail_price, price_unit, recorded_date
            FROM price_records
            WHERE recorded_date = (SELECT MAX(recorded_date) FROM latest_two_dates)
              AND retail_price IS NOT NULL
        ),
        yesterday AS (
            SELECT commodity, county, market, retail_price
            FROM price_records
            WHERE recorded_date = (SELECT MIN(recorded_date) FROM latest_two_dates)
              AND retail_price IS NOT NULL
        )
        SELECT
            t.commodity,
            t.county,
            t.market,
            t.retail_price,
            t.price_unit,
            y.retail_price AS prev_price,
            ROUND(
                CAST(((t.retail_price - y.retail_price) / y.retail_price * 100) AS numeric), 1
            ) AS change_pct
        FROM today t
        JOIN yesterday y
          ON t.commodity = y.commodity
         AND t.county    = y.county
         AND t.market    = y.market
        WHERE y.retail_price > 0
        ORDER BY ABS((t.retail_price - y.retail_price) / y.retail_price) DESC
        LIMIT :limit
    """)
    result = await db.execute(q, {"limit": limit})
    rows   = result.mappings().all()

    response = [dict(r) for r in rows]
    await set_cached(cache_key, response, ttl=settings.cache_ttl_summary)
    return response
