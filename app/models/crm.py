"""
app/models/crm.py
=================
SQLAlchemy 2.0 mapped-column ORM — every table in the NexusCRM schema.

Database Schema (PostgreSQL):
─────────────────────────────
  contacts          — people / lead records
  deals             — opportunities tied to a contact
  activities        — audit log (emails, calls, notes, stage changes)
  automation_rules  — webhook / trigger rules toggled via HTMX

Relationships:
  Contact  1──* Deal
  Contact  1──* Activity
  Deal     *──1 Contact  (FK: deals.contact_id → contacts.id)
  Activity *──1 Contact  (FK: activities.contact_id → contacts.id)
"""

import enum
from datetime import datetime
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────
class ActivityType(str, enum.Enum):
    email  = "email"
    call   = "call"
    note   = "note"
    deal   = "deal"

class PipelineStage(str, enum.Enum):
    prospect  = "Prospect"
    qualified = "Qualified"
    demo      = "Demo"
    proposal  = "Proposal"
    negotiate = "Negotiate"
    closed    = "Closed"

class Segment(str, enum.Enum):
    smb        = "SMB"
    mid_market = "Mid-Market"
    enterprise = "Enterprise"

class LeadStatus(str, enum.Enum):
    new         = "New"
    contacted   = "Contacted"
    qualified   = "Qualified"
    converted   = "Converted"
    lost        = "Lost"

from sqlalchemy import (
    Boolean, DateTime, Float,
    ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── contacts ──────────────────────────────────────────────────────────────────
class Contact(Base):
    """
    Central entity. One contact can have multiple deals and activity logs.
    The `score` column is written by services/scorer.py (Scikit-Learn model).
    """
    __tablename__ = "contacts"

    id           : Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    lead_name    : Mapped[str]           = mapped_column(String(120), nullable=False)
    company_name : Mapped[str]           = mapped_column(String(120), nullable=False)
    email        : Mapped[Optional[str]] = mapped_column(String(200), unique=True)
    segment      : Mapped[str]           = mapped_column(String(30),  default="SMB")
    status       : Mapped[str]           = mapped_column(String(20),  default="New")
    score        : Mapped[int]           = mapped_column(Integer,     default=50)
    value        : Mapped[float]         = mapped_column(Float,       default=0.0)

    # ML feature signals — raw inputs fed to the GradientBoosting model
    email_opens   : Mapped[int]   = mapped_column(Integer, default=0)
    page_visits   : Mapped[int]   = mapped_column(Integer, default=0)
    calls_made    : Mapped[int]   = mapped_column(Integer, default=0)
    response_rate : Mapped[float] = mapped_column(Float,   default=0.0)  # 0–1

    created_at : Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at : Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                  onupdate=func.now())

    # relationships
    deals      : Mapped[list["Deal"]]     = relationship(back_populates="contact",
                                                         cascade="all, delete-orphan")
    activities : Mapped[list["Activity"]] = relationship(back_populates="contact",
                                                         cascade="all, delete-orphan")


# ── deals ─────────────────────────────────────────────────────────────────────
class Deal(Base):
    """
    Sales opportunity. `stage` drives the Kanban column.
    Advancing a stage is done via POST /deal/advance/{id} (HTMX).
    `win_probability` is bumped +15 pts per stage advance (capped at 95).
    """
    __tablename__ = "deals"

    id              : Mapped[int]                = mapped_column(Integer, primary_key=True, index=True)
    contact_id      : Mapped[int]                = mapped_column(ForeignKey("contacts.id"), nullable=False)
    company_name    : Mapped[str]                = mapped_column(String(120), nullable=False)
    value           : Mapped[float]              = mapped_column(Float, nullable=False)
    stage           : Mapped[str]                = mapped_column(String(30), default="Prospect")
    win_probability : Mapped[int]                = mapped_column(Integer, default=20)
    service_type    : Mapped[str]                = mapped_column(String(80), default="Full Suite")
    rep_initials    : Mapped[str]                = mapped_column(String(5),  default="AK")
    closed_at       : Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at      : Mapped[datetime]           = mapped_column(DateTime, server_default=func.now())

    # relationships
    contact : Mapped["Contact"] = relationship(back_populates="deals")


# ── activities ────────────────────────────────────────────────────────────────
class Activity(Base):
    """
    Immutable audit log. Rows are INSERT-only; never updated or deleted.
    `action_type` maps to icon classes in activities.html (email|call|note|deal).
    """
    __tablename__ = "activities"

    id           : Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    contact_id   : Mapped[int]      = mapped_column(ForeignKey("contacts.id"), nullable=False)
    action_type  : Mapped[str]      = mapped_column(String(20))
    content      : Mapped[str]      = mapped_column(Text)
    rep_initials : Mapped[str]      = mapped_column(String(5), default="AK")
    is_read      : Mapped[bool]     = mapped_column(Boolean, default=False)
    occurred_at  : Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    contact : Mapped["Contact"] = relationship(back_populates="activities")


# ── automation_rules ──────────────────────────────────────────────────────────
class AutomationRule(Base):
    """
    Webhook / trigger rule. `is_active` is toggled live via
    HTMX POST /automation/toggle/{id} — no page reload needed.
    """
    __tablename__ = "automation_rules"

    id               : Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    rule_name        : Mapped[str]      = mapped_column(String(120), nullable=False)
    trigger_event    : Mapped[str]      = mapped_column(String(80))
    action_execution : Mapped[str]      = mapped_column(String(200))
    is_active        : Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at       : Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
