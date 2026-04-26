from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional


# ── Price Records ────────────────────────────────────────────────────────────

class PriceRecordOut(BaseModel):
    id:              int
    commodity:       str
    classification:  Optional[str] = None
    grade:           Optional[str] = None
    market:          str
    county:          str
    wholesale_price: Optional[float] = None
    retail_price:    Optional[float] = None
    price_unit:      Optional[str]   = None
    supply_volume:   Optional[float] = None
    recorded_date:   date

    model_config = {"from_attributes": True}


class PriceListResponse(BaseModel):
    total:   int
    page:    int
    limit:   int
    data:    list[PriceRecordOut]


# ── Trend / Aggregated ────────────────────────────────────────────────────────

class TrendPoint(BaseModel):
    recorded_date:   date
    county:          str
    avg_retail:      Optional[float] = None
    avg_wholesale:   Optional[float] = None
    total_supply:    Optional[float] = None
    data_points:     int = 0


class CountyComparePoint(BaseModel):
    county:          str
    avg_retail:      Optional[float] = None
    avg_wholesale:   Optional[float] = None
    latest_date:     Optional[date]  = None
    market_count:    int = 0


# ── Commodities / Counties ────────────────────────────────────────────────────

class CommoditySummary(BaseModel):
    commodity:      str
    latest_date:    Optional[date]  = None
    avg_retail:     Optional[float] = None
    avg_wholesale:  Optional[float] = None
    market_count:   int = 0
    county_count:   int = 0


class CountySummary(BaseModel):
    county:         str
    market_count:   int = 0
    commodity_count:int = 0
    latest_date:    Optional[date] = None


# ── Stats ─────────────────────────────────────────────────────────────────────

class TopMover(BaseModel):
    commodity:    str
    county:       str
    market:       str
    retail_price: Optional[float] = None
    price_unit:   Optional[str]   = None
    change_pct:   float           = 0.0
    direction:    str             = "up"   # "up" | "down"


class StatsSummary(BaseModel):
    latest_date:      Optional[date]    = None
    total_records:    int               = 0
    county_count:     int               = 0
    commodity_count:  int               = 0
    top_movers:       list[TopMover]    = []
    last_scrape:      Optional[str]     = None


# ── Scraper ───────────────────────────────────────────────────────────────────

class ScrapeRunOut(BaseModel):
    id:               int
    run_at:           datetime
    status:           str
    records_inserted: int
    records_skipped:  int
    duration_seconds: Optional[float] = None
    error_msg:        Optional[str]   = None

    model_config = {"from_attributes": True}


class ScrapeResult(BaseModel):
    status:           str
    records_inserted: int
    records_skipped:  int
    duration_seconds: float
    errors:           list[str] = []
