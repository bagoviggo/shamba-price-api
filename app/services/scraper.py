"""
KAMIS Scraper
─────────────
Fetches market price data from https://kamis.kilimo.go.ke/site/market
by paginating offset-by-offset (KAMIS ignores the ?entries= param for
large values — it's JavaScript-driven). We walk /site/market, then
/site/market/10?, /site/market/20? etc. until we get an empty page.
"""

import asyncio
import logging
import time
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.cache import invalidate_all

logger   = logging.getLogger(__name__)
settings = get_settings()

PAGE_SIZE = 10   # KAMIS always returns 10 rows per page regardless of ?entries=


# ── Price / volume parsers ────────────────────────────────────────────────────

def _parse_price(raw: str) -> tuple[Optional[float], Optional[str]]:
    if not raw:
        return None, None
    raw = raw.strip()
    if raw in ("-", "", "N/A"):
        return None, None
    parts = raw.split("/", 1)
    try:
        value = float(parts[0].replace(",", ""))
        unit  = parts[1].strip() if len(parts) > 1 else None
        return value, unit
    except (ValueError, IndexError):
        return None, None


def _parse_volume(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw.strip().replace(",", "")) or None
    except ValueError:
        return None


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return date.today()


def _clean(val: str) -> Optional[str]:
    v = val.strip() if val else None
    return v if v and v not in ("-", "") else None


# ── HTML table parser ─────────────────────────────────────────────────────────

def parse_table(html: str) -> list[dict]:
    """
    Expected columns:
      Commodity | Classification | Grade | Sex | Market |
      Wholesale | Retail | Supply Volume | County | Date
    """
    soup  = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 9:
            continue

        if len(cells) >= 10:
            commodity, classification, grade = cells[0], cells[1], cells[2]
            market = cells[4]
            wholesale_raw, retail_raw, supply_raw = cells[5], cells[6], cells[7]
            county   = cells[8]
            date_raw = cells[9] if len(cells) > 9 else None
        else:
            commodity, classification, grade = cells[0], cells[1], cells[2]
            market = cells[3]
            wholesale_raw, retail_raw, supply_raw = cells[4], cells[5], cells[6]
            county   = cells[7]
            date_raw = cells[8] if len(cells) > 8 else None

        w_price, unit = _parse_price(wholesale_raw)
        r_price, _    = _parse_price(retail_raw)

        row = {
            "commodity":       _clean(commodity),
            "classification":  _clean(classification),
            "grade":           _clean(grade),
            "market":          _clean(market),
            "county":          _clean(county),
            "wholesale_price": w_price,
            "retail_price":    r_price,
            "price_unit":      unit,
            "supply_volume":   _parse_volume(supply_raw),
            "recorded_date":   _parse_date(date_raw),
        }

        if row["commodity"] and row["market"] and row["county"]:
            rows.append(row)

    return rows


# ── HTTP fetch ────────────────────────────────────────────────────────────────

async def fetch_page(client: httpx.AsyncClient, offset: int = 0, product_id: int = 2) -> str:
    base = settings.kamis_base_url
    url  = f"{base}/site/market/{offset}?" if offset > 0 else f"{base}/site/market"
    headers = {
        "User-Agent": "ShambaAI/1.0 (Agricultural Market Research)",
        "Accept":     "text/html,application/xhtml+xml",
    }
    resp = await client.get(
        url,
        params={"product": product_id, "per_page": PAGE_SIZE},
        headers=headers,
        timeout=settings.scraper_request_timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text

# ── DB upsert ────────────────────────────────────────────────────────────────

UPSERT_SQL = text("""
    INSERT INTO price_records
        (commodity, classification, grade, market, county,
         wholesale_price, retail_price, price_unit, supply_volume, recorded_date)
    VALUES
        (:commodity, :classification, :grade, :market, :county,
         :wholesale_price, :retail_price, :price_unit, :supply_volume, :recorded_date)
    ON CONFLICT (commodity, market, recorded_date, classification)
    DO NOTHING
""")


async def _upsert_batch(session: AsyncSession, records: list[dict]) -> tuple[int, int]:
    inserted = skipped = 0
    for rec in records:
        result = await session.execute(UPSERT_SQL, rec)
        if result.rowcount:
            inserted += 1
        else:
            skipped += 1
    await session.commit()
    return inserted, skipped


# ── Main scrape orchestrator ──────────────────────────────────────────────────

async def run_scrape(session: AsyncSession) -> dict:
    t_start    = time.monotonic()
    total_ins  = 0
    total_skip = 0
    errors: list[str] = []

    try:
        async with httpx.AsyncClient(verify=False) as client:
            for product_id in range(2, 274):
                offset = 0
                logger.info("Scraping product_id=%d ...", product_id)

                while True:
                    try:
                        html    = await fetch_page(client, offset=offset, product_id=product_id)
                        records = parse_table(html)
                        logger.info("  product=%d offset=%d rows=%d", product_id, offset, len(records))

                        if records and all(r["recorded_date"].year < 2024 for r in records):
                            logger.info("Reached pre-2024 data at product=%d offset=%d — stopping", product_id, offset)
                            break
                        records = [r for r in records if r["recorded_date"].year >= 2024]
                    except Exception as e:
                        msg = f"Fetch error product={product_id} offset={offset}: {e}"
                        logger.error(msg)
                        errors.append(msg)
                        break

                    if not records:
                        break

                    ins, skip = await _upsert_batch(session, records)
                    total_ins  += ins
                    total_skip += skip

                    if len(records) < PAGE_SIZE:
                        break

                    offset += PAGE_SIZE
                    await asyncio.sleep(settings.scraper_request_delay_seconds)

    except Exception as e:
        msg = f"Scrape failed: {e}"
        logger.exception(msg)
        errors.append(msg)
        await session.rollback()

    duration = round(time.monotonic() - t_start, 2)
    status   = "failed" if (not total_ins and errors) else ("partial" if errors else "success")

    try:
        await session.execute(text("""
            INSERT INTO scrape_runs
                (run_at, status, records_inserted, records_skipped, duration_seconds, error_msg)
            VALUES (NOW(), :status, :ins, :skip, :dur, :err)
        """), {"status": status, "ins": total_ins, "skip": total_skip,
               "dur": duration, "err": "; ".join(errors[:5]) if errors else None})
        await session.commit()
    except Exception as e:
        logger.warning("Could not log scrape run: %s", e)

    if status in ("success", "partial"):
        busted = await invalidate_all()
        logger.info("Cache busted: %d keys removed", busted)

    result = {"status": status, "records_inserted": total_ins,
              "records_skipped": total_skip, "duration_seconds": duration, "errors": errors}
    logger.info("Scrape complete: %s", result)
    return result
