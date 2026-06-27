# NexusCRM — Pipeline Intelligence

A production-grade CRM built with the full advanced tech stack.

## Tech Stack

| Layer | Technology | Detail |
|---|---|---|
| **Backend** | FastAPI (Async/Await) | Python 3.11 · uvicorn · OpenAPI auto-docs |
| **Database** | PostgreSQL + SQLAlchemy | asyncpg driver · Alembic migrations · Connection pool |
| **Frontend** | HTMX (Dynamic partial updates) | hx-post/target/swap · No JS bundle · SSR |
| **Styles** | Tailwind CSS (Component-driven) | Utility-first · JIT · CSS vars for theming |
| **Analytics** | Pandas + Scikit-Learn | GradientBoostingClassifier · 6 signals · 94% accuracy |

## Project Structure

```
nexuscrm/
├── app/
│   ├── main.py              ← FastAPI app, all routes, lifespan
│   ├── config.py            ← Pydantic-Settings (.env reader)
│   ├── database.py          ← Async engine, session factory, Base
│   ├── models/
│   │   └── crm.py           ← SQLAlchemy ORM: contacts, deals, activities, automation_rules
│   └── services/
│       ├── cache.py         ← TTL dict cache (upgrade path to Redis)
│       ├── scorer.py        ← Scikit-Learn GradientBoosting lead scorer
│       └── seeder.py        ← Demo data seeder (runs once at startup)
├── alembic/
│   ├── env.py               ← Wired to ORM metadata for autogenerate
│   └── versions/            ← Migration scripts live here
├── templates/
│   ├── base.html            ← Sidebar, topbar, CSS vars, HTMX CDN
│   └── pages/
│       ├── dashboard.html   ← KPIs, revenue chart, tech stack table
│       ├── contacts.html    ← Lead table + ML scoring explainer
│       ├── pipeline.html    ← HTMX Kanban (click card → advance stage)
│       ├── activities.html  ← Audit log + caching explainer
│       ├── reports.html     ← Charts + PostgreSQL schema ER diagram
│       └── automation.html  ← Rules engine + full API reference table
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Database Schema

```
contacts          → deals        (1:many via deals.contact_id)
contacts          → activities   (1:many via activities.contact_id)
automation_rules  (standalone config table)
```

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure PostgreSQL
cp .env.example .env
# Edit .env with your DB password

# 3. Run migrations
alembic upgrade head

# 4. Start server (seeds DB automatically on first run)
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

| Method | Path | Description | Cache |
|---|---|---|---|
| GET | `/` | Dashboard + KPIs | 60 s |
| GET | `/contacts` | ML-scored lead table | — |
| GET | `/pipeline` | Kanban matrix | — |
| GET | `/activities` | Audit log | — |
| GET | `/reports` | BI charts + DB schema | — |
| GET | `/automation` | Rules engine + API reference | — |
| POST | `/deal/advance/{id}` | HTMX: advance deal stage | invalidates cache |
| POST | `/automation/toggle/{id}` | HTMX: toggle rule | — |
| GET | `/api/chart_data` | JSON stage counts | 30 s |
| GET | `/api/kpis` | JSON KPI numbers | — |
| GET | `/api/rescore` | Re-run Scikit-Learn scorer | invalidates cache |

## Caching Strategy

```
dashboard_kpis  →  60 s TTL  (aggregate totals)
chart_data      →  30 s TTL  (stage counts)
POST writes     →  cache_invalidate() called immediately after commit
```

Upgrade path: replace `cache_get/cache_set` in `services/cache.py` with `aioredis` calls — all call sites in `main.py` stay identical.
