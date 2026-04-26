from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime,
    Text, UniqueConstraint, Index, func
)
from app.database import Base
from datetime import datetime


class PriceRecord(Base):
    __tablename__ = "price_records"

    id               = Column(Integer, primary_key=True, index=True)
    commodity        = Column(String(120), nullable=False)
    classification   = Column(String(120))
    grade            = Column(String(60))
    market           = Column(String(120), nullable=False)
    county           = Column(String(60), nullable=False)
    wholesale_price  = Column(Numeric(10, 2))
    retail_price     = Column(Numeric(10, 2))
    price_unit       = Column(String(30))       # Kg, Lt, Tray(30) …
    supply_volume    = Column(Numeric(14, 2))
    recorded_date    = Column(Date, nullable=False)
    scraped_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "commodity", "market", "recorded_date", "classification",
            name="uq_price_record",
        ),
        # Fast lookups by the most common filter combinations
        Index("ix_pr_commodity",     "commodity"),
        Index("ix_pr_county",        "county"),
        Index("ix_pr_date",          "recorded_date"),
        Index("ix_pr_commodity_date","commodity", "recorded_date"),
        Index("ix_pr_county_date",   "county",    "recorded_date"),
    )

    def to_dict(self):
        return {
            "id":              self.id,
            "commodity":       self.commodity,
            "classification":  self.classification,
            "grade":           self.grade,
            "market":          self.market,
            "county":          self.county,
            "wholesale_price": float(self.wholesale_price) if self.wholesale_price else None,
            "retail_price":    float(self.retail_price)    if self.retail_price    else None,
            "price_unit":      self.price_unit,
            "supply_volume":   float(self.supply_volume)   if self.supply_volume   else None,
            "recorded_date":   self.recorded_date.isoformat() if self.recorded_date else None,
        }


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id               = Column(Integer, primary_key=True)
    run_at           = Column(DateTime, default=datetime.utcnow)
    status           = Column(String(20))    # success | partial | failed
    records_inserted = Column(Integer, default=0)
    records_skipped  = Column(Integer, default=0)
    duration_seconds = Column(Numeric(8, 2))
    error_msg        = Column(Text)

    def to_dict(self):
        return {
            "id":               self.id,
            "run_at":           self.run_at.isoformat() if self.run_at else None,
            "status":           self.status,
            "records_inserted": self.records_inserted,
            "records_skipped":  self.records_skipped,
            "duration_seconds": float(self.duration_seconds) if self.duration_seconds else None,
            "error_msg":        self.error_msg,
        }
