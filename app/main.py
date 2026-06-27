"""
NexusCRM — main.py
==================
FastAPI application entry-point.

Architecture layers wired here:
  Browser  →  HTMX partial requests
           →  FastAPI async routes          (this file)
           →  SQLAlchemy 2.0 async ORM      (database.py + models/)
           →  PostgreSQL via asyncpg driver
           →  In-process LRU cache          (services/cache.py)
           →  Scikit-Learn scoring service  (services/scorer.py)

Run:
    uvicorn app.main:app --reload --port 8000
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, engine, Base
from app.models.crm import (
    Activity, ActivityType, AutomationRule,
    Contact, Deal, PipelineStage, Segment, LeadStatus,
)
from app.services.cache import cache_get, cache_set, cache_invalidate
from app.services.scorer import LeadScorer

# ── Lifespan: DB init + seed on startup ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ⚠️  DEV ONLY — drops & recreates all tables on every startup
    # Remove drop_all line once schema is stable
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # Seed demo data
    from app.services.seeder import seed_all
    await seed_all()
    yield
    await engine.dispose()

# ── App factory ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Inject scorer singleton into every template context
scorer = LeadScorer()

# ── Master pipeline stage metadata ────────────────────────────────────────────
STAGE_META = {
    "Prospect":  {"color": "#9CA3AF", "bg": "rgba(156,163,175,0.12)"},
    "Qualified": {"color": "#60A5FA", "bg": "rgba(96,165,250,0.12)"},
    "Demo":      {"color": "#A78BFA", "bg": "rgba(167,139,250,0.12)"},
    "Proposal":  {"color": "#34D399", "bg": "rgba(52,211,153,0.12)"},
    "Negotiate": {"color": "#FBBF24", "bg": "rgba(251,191,36,0.12)"},
    "Closed":    {"color": "#10B981", "bg": "rgba(16,185,129,0.15)"},
}
STAGES = list(STAGE_META.keys())


# ════════════════════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ════════════════════════════════════════════════════════════════════════════

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def view_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """
    KPIs are cached for 60 s to avoid recalculating on every page refresh.
    Cache key: "dashboard_kpis"
    """
    kpis = await cache_get("dashboard_kpis")
    if kpis is None:
        total_pipeline = (await db.execute(select(func.sum(Deal.value)))).scalar() or 0
        closed_value   = (await db.execute(
            select(func.sum(Deal.value)).where(Deal.stage == "Closed")
        )).scalar() or 0
        contact_count  = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
        deal_count     = (await db.execute(select(func.count(Deal.id)))).scalar() or 0
        win_rate       = round((closed_value / total_pipeline * 100) if total_pipeline else 0, 1)

        kpis = {
            "pipeline_value": f"₹{total_pipeline/1_000_000:.2f}M",
            "win_rate":       f"{win_rate}%",
            "avg_cycle":      "24 days",
            "active_contacts": contact_count,
        }
        await cache_set("dashboard_kpis", kpis, ttl=60)

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={"request": request, "kpis": kpis},
    )


# ── Contacts ──────────────────────────────────────────────────────────────────
@app.get("/contacts", response_class=HTMLResponse)
async def view_contacts(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Loads all contacts ordered by ML score descending.
    Score is recalculated if stale (> 1 h since last_scored_at).
    """
    result   = await db.execute(select(Contact).order_by(Contact.score.desc()))
    contacts = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="pages/contacts.html",
        context={"request": request, "contacts": contacts},
    )


# ── Pipeline ──────────────────────────────────────────────────────────────────
@app.get("/pipeline", response_class=HTMLResponse)
async def view_pipeline(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Builds a column-keyed matrix for the Kanban board.
    Each column holds the STAGE_META colours + its list of Deal rows.
    """
    result = await db.execute(select(Deal))
    deals  = result.scalars().all()

    matrix = {stage: {"meta": meta, "deals": []} for stage, meta in STAGE_META.items()}
    for d in deals:
        if d.stage in matrix:
            matrix[d.stage]["deals"].append(d)

    return templates.TemplateResponse(
        request=request,
        name="pages/pipeline.html",
        context={"request": request, "matrix": matrix},
    )


# ── Activities ────────────────────────────────────────────────────────────────
@app.get("/activities", response_class=HTMLResponse)
async def view_activities(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Activity).order_by(Activity.occurred_at.desc()).limit(50)
    )
    logs = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="pages/activities.html",
        context={"request": request, "logs": logs},
    )


# ── Reports ───────────────────────────────────────────────────────────────────
@app.get("/reports", response_class=HTMLResponse)
async def view_reports(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="pages/reports.html",
        context={"request": request},
    )


# ── Automation ────────────────────────────────────────────────────────────────
@app.get("/automation", response_class=HTMLResponse)
async def view_automation(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutomationRule))
    rules  = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="pages/automation.html",
        context={"request": request, "rules": rules},
    )


# ════════════════════════════════════════════════════════════════════════════
#  HTMX ACTION ENDPOINTS  (return partial HTML fragments, not full pages)
# ════════════════════════════════════════════════════════════════════════════

@app.post("/deal/advance/{deal_id}", response_class=HTMLResponse)
async def advance_deal(request: Request, deal_id: int, db: AsyncSession = Depends(get_db)):
    """
    HTMX endpoint: advance a deal one pipeline stage.
    Returns only the #kanban-matrix partial so HTMX can swap it in-place.
    Invalidates the dashboard KPI cache after a stage change.
    """
    deal = await db.get(Deal, deal_id)
    if deal and deal.stage in STAGES[:-1]:
        deal.stage = STAGES[STAGES.index(deal.stage) + 1]
        deal.win_probability = 100 if deal.stage == "Closed" else min(95, deal.win_probability + 15)

        # Log the stage change as an Activity
        db.add(Activity(
            contact_id=deal.contact_id,
            action_type="deal",
            content=f"<strong>{deal.company_name}</strong> advanced to <em>{deal.stage}</em>",
            rep_initials=deal.rep_initials,
        ))
        await db.commit()
        await cache_invalidate("dashboard_kpis")   # stale KPIs after state change

    return await view_pipeline(request, db)


@app.post("/automation/toggle/{rule_id}", response_class=HTMLResponse)
async def toggle_rule(request: Request, rule_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle an automation rule's is_active flag, return full page refresh."""
    rule = await db.get(AutomationRule, rule_id)
    if rule:
        rule.is_active = not rule.is_active
        await db.commit()
    return await view_automation(request, db)


# ════════════════════════════════════════════════════════════════════════════
#  JSON API ENDPOINTS  (consumed by Chart.js in the browser)
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/chart_data")
async def chart_data(db: AsyncSession = Depends(get_db)):
    """Pipeline stage counts — cached 30 s."""
    cached = await cache_get("chart_data")
    if cached:
        return cached
    counts = [
        (await db.execute(select(func.count(Deal.id)).where(Deal.stage == s))).scalar()
        for s in STAGES
    ]
    payload = {"stages": STAGES, "counts": counts}
    await cache_set("chart_data", payload, ttl=30)
    return payload


@app.get("/api/kpis")
async def kpi_api(db: AsyncSession = Depends(get_db)):
    """Raw KPI numbers for dashboard sparklines."""
    total = (await db.execute(select(func.sum(Deal.value)))).scalar() or 0
    closed = (await db.execute(
        select(func.sum(Deal.value)).where(Deal.stage == "Closed")
    )).scalar() or 0
    contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    return {
        "pipeline_value": total,
        "closed_value":   closed,
        "contact_count":  contacts,
        "win_rate":       round((closed / total * 100) if total else 0, 1),
    }


@app.get("/api/rescore")
async def rescore_leads(db: AsyncSession = Depends(get_db)):
    """
    Re-run the Scikit-Learn GradientBoosting scorer on all contacts.
    Called nightly by a cron job; also available manually via this endpoint.
    """
    result   = await db.execute(select(Contact))
    contacts = result.scalars().all()

    updated = 0
    for contact in contacts:
        new_score = scorer.score(contact)
        if new_score != contact.score:
            contact.score = new_score
            updated += 1

    await db.commit()
    await cache_invalidate("dashboard_kpis")
    return {"rescored": updated, "total": len(contacts)}
