import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import create_tables
from app.scheduler import start_scheduler
from app.routers import prices, commodities, counties, stats, scraper

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger   = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌱 Shamba AI API starting up...")

    # Auto-create tables in dev (use Alembic migrations in production)
    if settings.environment == "development":
        await create_tables()
        logger.info("✅ Database tables ready")

    start_scheduler()

    yield  # — app is running —

    logger.info("👋 Shamba AI API shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Shamba AI — Agricultural Market API",
    description=(
        "Real-time Kenyan agricultural commodity prices sourced from KAMIS "
        "(Kenya Agricultural Market Information System). "
        "Covers 47 counties, 180+ commodities, updated daily."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS — allow Next.js frontend (and all origins in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

PREFIX = "/api/v1"

app.include_router(prices.router,      prefix=f"{PREFIX}/prices",      tags=["Prices"])
app.include_router(commodities.router, prefix=f"{PREFIX}/commodities", tags=["Commodities"])
app.include_router(counties.router,    prefix=f"{PREFIX}/counties",    tags=["Counties"])
app.include_router(stats.router,       prefix=f"{PREFIX}/stats",       tags=["Stats"])
app.include_router(scraper.router,     prefix=f"{PREFIX}/scraper",     tags=["Scraper"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0", "env": settings.environment}


# ── Global error handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
