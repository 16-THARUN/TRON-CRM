"""
app/services/seeder.py
======================
One-shot demo data seeder — skips if tables already populated.
Called from the FastAPI lifespan startup hook in main.py.
"""

from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.crm import Contact, Deal, Activity, AutomationRule


async def seed_all():
    async with AsyncSessionLocal() as db:
        # ── Contacts ──────────────────────────────────────────────────────
        if not (await db.execute(select(Contact))).first():
            contacts = [
                Contact(lead_name="Priya Mehta",  company_name="Orbital Finance",
                        segment="Enterprise", status="Hot",  score=94, value=280000,
                        email_opens=22, page_visits=41, calls_made=6, response_rate=0.88),
                Contact(lead_name="Rohan Das",    company_name="Atlas Media",
                        segment="Enterprise", status="Hot",  score=87, value=310000,
                        email_opens=18, page_visits=35, calls_made=5, response_rate=0.80),
                Contact(lead_name="Sana Rauf",    company_name="Crest Retail",
                        segment="SMB",        status="Warm", score=71, value=95000,
                        email_opens=12, page_visits=20, calls_made=3, response_rate=0.60),
                Contact(lead_name="Kabir Joshi",  company_name="Lumio Health",
                        segment="Startup",    status="New",  score=63, value=120000,
                        email_opens=8,  page_visits=15, calls_made=2, response_rate=0.50),
                Contact(lead_name="Asha Pillai",  company_name="Pragma Cloud",
                        segment="SMB",        status="Cold", score=42, value=180000,
                        email_opens=3,  page_visits=5,  calls_made=1, response_rate=0.20),
            ]
            db.add_all(contacts)
            await db.flush()   # get IDs assigned before FK use

            # ── Deals ─────────────────────────────────────────────────────
            db.add_all([
                Deal(contact_id=contacts[0].id, company_name="Vertex Systems",   value=48000,  stage="Prospect",  win_probability=20, service_type="ERP Expansion", rep_initials="AK"),
                Deal(contact_id=contacts[4].id, company_name="Lumio Health",     value=120000, stage="Prospect",  win_probability=25, service_type="Platform",      rep_initials="PR"),
                Deal(contact_id=contacts[0].id, company_name="Orbital Finance",  value=280000, stage="Qualified", win_probability=45, service_type="Suite Pro",     rep_initials="NM"),
                Deal(contact_id=contacts[2].id, company_name="Crest Retail",     value=95000,  stage="Qualified", win_probability=50, service_type="CRM Migrate",   rep_initials="SR"),
                Deal(contact_id=contacts[1].id, company_name="Nexus Logistics",  value=540000, stage="Demo",      win_probability=65, service_type="Enterprise",    rep_initials="AK"),
                Deal(contact_id=contacts[0].id, company_name="Zenith Corp",      value=420000, stage="Proposal",  win_probability=78, service_type="Renewal+",      rep_initials="NM"),
                Deal(contact_id=contacts[1].id, company_name="Atlas Media",      value=310000, stage="Negotiate", win_probability=88, service_type="Scale",         rep_initials="AK"),
                Deal(contact_id=contacts[0].id, company_name="Meridian Inc",     value=680000, stage="Closed",    win_probability=100,service_type="Full Suite",    rep_initials="PR"),
            ])

            # ── Activities ────────────────────────────────────────────────
            db.add_all([
                Activity(contact_id=contacts[0].id, action_type="deal",  content="<strong>Meridian Inc</strong> deal closed for ₹680K", rep_initials="PR"),
                Activity(contact_id=contacts[0].id, action_type="email", content="Proposal sent to <strong>Zenith Corp</strong> — ₹420K renewal", rep_initials="NM"),
                Activity(contact_id=contacts[2].id, action_type="call",  content="30-min discovery call logged with <strong>Sana Rauf</strong>", rep_initials="SR"),
                Activity(contact_id=contacts[1].id, action_type="note",  content="Meeting notes added — <strong>Nexus Logistics</strong> demo recap", rep_initials="AK"),
                Activity(contact_id=contacts[0].id, action_type="email", content="Proposal sent to <strong>Zenith Corp</strong> — ₹420K renewal", rep_initials="NM"),
                Activity(contact_id=contacts[3].id, action_type="call",  content="Inbound call from <strong>Kabir Joshi</strong> — Lumio Health inquired about pricing", rep_initials="PR"),
            ])

            # ── Automation Rules ──────────────────────────────────────────
            db.add_all([
                AutomationRule(rule_name="Hot Lead Alert",        trigger_event="score > 85",          action_execution="Slack notify #sales-hot-leads",  is_active=True),
                AutomationRule(rule_name="Deal Stale Warning",    trigger_event="stage unchanged 7d",  action_execution="Email rep + manager",            is_active=True),
                AutomationRule(rule_name="Close Won Celebration", trigger_event="stage = Closed",      action_execution="Post to #wins + update HubSpot", is_active=True),
                AutomationRule(rule_name="Cold Lead Re-engage",   trigger_event="status = Cold 14d",   action_execution="Enroll in nurture sequence",     is_active=False),
                AutomationRule(rule_name="Nightly ML Rescore",    trigger_event="cron 02:00 UTC",      action_execution="GET /api/rescore",               is_active=True),
            ])

            await db.commit()
