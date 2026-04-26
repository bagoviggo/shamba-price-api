# Shamba AI — FastAPI Backend

Real-time Kenyan agricultural commodity price API, scraped daily from KAMIS.

## Stack
- **FastAPI** — async Python web framework
- **PostgreSQL** — price records storage
- **Redis** — response caching
- **SQLAlchemy (async)** — ORM + query layer
- **Alembic** — database migrations
- **APScheduler** — daily 6 AM scrape cron
- **httpx + BeautifulSoup** — KAMIS HTML scraper

---

## Quick Start (Local)

### 1. Prerequisites
- Python 3.11+
- Docker Desktop (for Postgres + Redis)

### 2. Clone & install
```bash
git clone <your-repo>
cd shamba-api

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Start databases
```bash
docker-compose up -d
# Postgres on :5432, Redis on :6379
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY if you're using the AI endpoints
```

### 5. Run database migrations
```bash
alembic upgrade head
```

### 6. Start the API
```bash
uvicorn app.main:app --reload
```

API is live at **http://localhost:8000**
Swagger docs at **http://localhost:8000/docs**

---

## Seed Data (First Run)

Trigger the scraper manually to populate the database:
```bash
curl -X POST http://localhost:8000/api/v1/scraper/run
```

This fetches the latest KAMIS data. Takes 10–30 seconds depending on how many
pages need to be fetched. Check progress:
```bash
curl http://localhost:8000/api/v1/scraper/status
```

---

## API Reference

### Health
```
GET /health
```

### Prices
```
GET /api/v1/prices
    ?commodity=Tomatoes
    &county=Nairobi
    &market=Gikomba
    &date_from=2026-03-01
    &date_to=2026-03-09
    &page=1
    &limit=50

GET /api/v1/prices/daily
    ?county=Nakuru
    ?commodity=Dry+Maize

GET /api/v1/prices/commodity/{name}/trend
    ?days=30

GET /api/v1/prices/compare
    ?commodity=Tomatoes
    &counties=Nairobi,Nakuru,Eldoret
    &days=7

GET /api/v1/prices/movers
    ?limit=10
```

### Commodities
```
GET /api/v1/commodities
GET /api/v1/commodities/{name}
```

### Counties
```
GET /api/v1/counties
GET /api/v1/counties/{name}/prices
GET /api/v1/counties/{name}/markets
```

### Stats
```
GET /api/v1/stats/summary
```

### Scraper (Admin)
```
POST /api/v1/scraper/run
GET  /api/v1/scraper/status
```

---

## Deploy to Railway

### 1. Create Railway project
```bash
npm install -g @railway/cli
railway login
railway init
```

### 2. Add Postgres + Redis plugins
From the Railway dashboard, click **New** → **Database** → add both PostgreSQL and Redis.
Railway automatically injects `DATABASE_URL` and `REDIS_URL` as environment variables.

### 3. Set environment variables
```bash
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set ENVIRONMENT=production
railway variables set KAMIS_BASE_URL=https://kamis.kilimo.go.ke
```

### 4. Deploy
```bash
railway up
```

Railway reads `railway.toml` which runs `alembic upgrade head` before starting uvicorn.

---

## Project Structure

```
shamba-api/
├── app/
│   ├── main.py          ← FastAPI app, CORS, lifespan
│   ├── config.py        ← Settings (pydantic-settings)
│   ├── database.py      ← SQLAlchemy async engine + session
│   ├── models.py        ← ORM table definitions
│   ├── schemas.py       ← Pydantic request/response models
│   ├── scheduler.py     ← APScheduler daily cron
│   ├── routers/
│   │   ├── prices.py    ← /prices endpoints
│   │   ├── commodities.py
│   │   ├── counties.py
│   │   ├── stats.py
│   │   └── scraper.py   ← /scraper/run + /scraper/status
│   └── services/
│       ├── scraper.py   ← KAMIS HTML scraper + DB upsert
│       └── cache.py     ← Redis get/set/invalidate
├── alembic/             ← DB migrations
├── docker-compose.yml   ← Local Postgres + Redis
├── railway.toml         ← Railway deploy config
├── requirements.txt
└── .env.example
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL async URL |
| `REDIS_URL` | ✅ | — | Redis URL |
| `ANTHROPIC_API_KEY` | Optional | — | For AI endpoints |
| `KAMIS_BASE_URL` | — | https://kamis.kilimo.go.ke | KAMIS source |
| `ENVIRONMENT` | — | development | `development` or `production` |
| `SCRAPER_ENTRIES_PER_PAGE` | — | 3000 | Records per KAMIS page fetch |
| `SCRAPER_REQUEST_DELAY_SECONDS` | — | 1.5 | Politeness delay between pages |

---

## Caching Strategy

| Endpoint | TTL | Bust trigger |
|---|---|---|
| `/prices` (filtered) | 1 hour | After scrape |
| `/prices/daily` | 1 hour | After scrape |
| `/prices/commodity/trend` | 6 hours | After scrape |
| `/prices/compare` | 2 hours | After scrape |
| `/stats/summary` | 30 min | After scrape |
| `/commodities` | 24 hours | After scrape |
| `/counties` | 24 hours | After scrape |

All caches are busted automatically after each successful scrape run.
