"""RepairXpert Industrial Automation — FastAPI diagnostic tool for field techs."""
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from indauto.diagnosis.engine import diagnose_fault, load_fault_db
from indauto.diagnosis.photo import analyze_photo
from indauto.parts.catalog import get_parts_for_category

# === PROCUREMENT ENGINE (auto-integrated) ===
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from procurement_routes import procurement_router
except ImportError:
    procurement_router = None

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

# ── 24/7 Revenue Loop + Cloud Worker (runs on Render, no local PC) ───────────
import threading
import time as _time

try:
    from revenue_loop import start_revenue_loop, get_log as get_revenue_log
    _revenue_thread = start_revenue_loop()
except Exception:
    _revenue_thread = None
    def get_revenue_log(): return ["revenue_loop.py not found"]

def _cloud_worker_loop():
    """Runs every 30 min inside the FastAPI process. Keeps services warm,
    processes cart recovery, checks Stripe balance. Zero extra cost."""
    import urllib.request
    _time.sleep(60)  # wait for app startup
    while True:
        try:
            # Keep all Render services warm (prevents cold start)
            for url in [
                "https://clawgrab.onrender.com/health",
                "https://us-debt-clock.onrender.com",
                "https://vendor-ad-network.onrender.com/health",
            ]:
                try:
                    urllib.request.urlopen(urllib.request.Request(
                        url, headers={"User-Agent": "CloudWorker/1.0"}), timeout=10)
                except Exception:
                    pass

            # Process cart recovery queue
            recovery_key = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
            if recovery_key:
                try:
                    req = urllib.request.Request(
                        "https://indautomation.onrender.com/api/recovery/process",
                        data=b"{}",
                        headers={"Content-Type": "application/json",
                                 "X-Recovery-Key": recovery_key},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=30)
                except Exception:
                    pass
        except Exception:
            pass
        _time.sleep(1800)  # 30 minutes

_worker = threading.Thread(target=_cloud_worker_loop, daemon=True, name="cloud-worker")
_worker.start()

# ── Stripe config (keys loaded from environment) ──────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

# Price IDs for each plan — set these in your environment after creating
# products in the Stripe Dashboard.
STRIPE_PRICE_IDS = {
    "pro": os.environ.get("STRIPE_PRICE_ID_PRO", ""),
    "enterprise": os.environ.get("STRIPE_PRICE_ID_ENTERPRISE", ""),
}

_stripe_available = False
if STRIPE_SECRET_KEY:
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        _stripe_available = True
    except ImportError:
        pass

_is_debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
app = FastAPI(
    title="RepairXpert IndAutomation",
    version="1.0.0",
    docs_url="/docs" if _is_debug else None,
    redoc_url="/redoc" if _is_debug else None,
    openapi_url="/openapi.json" if _is_debug else None,
)

# ── Request size limit middleware (CVE-2024-47874) ───────────────────────────
MAX_REQUEST_BODY = 10 * 1024 * 1024  # 10 MB

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware)

app.mount("/static", StaticFiles(directory=ROOT / "indauto" / "ui" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "indauto" / "ui" / "templates"))
templates.env.auto_reload = True

# Mount procurement router if available
if procurement_router:
    app.include_router(procurement_router)
    print("[PROCUREMENT] Router mounted at /api/procurement/*")

DB_PATH = ROOT / "data" / "diagnosis_log.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Stripe webhook + Resend config ───────────────────────────────────────────
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
LOGS_PATH = ROOT / "logs"
LOGS_PATH.mkdir(parents=True, exist_ok=True)

# Load equipment types for dropdowns
EQUIPMENT_DB_PATH = ROOT / "indauto" / "fault_db" / "equipment.json"


def _load_equipment():
    if EQUIPMENT_DB_PATH.exists():
        data = json.loads(EQUIPMENT_DB_PATH.read_text(encoding="utf-8"))
        return data.get("equipment", [])
    return []


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS diagnoses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        equipment_type TEXT,
        fault_code TEXT,
        symptoms TEXT,
        fault_name TEXT,
        diagnosis TEXT,
        fix_steps TEXT,
        photo_analysis TEXT,
        severity TEXT,
        confidence REAL,
        source TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS checkout_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        email TEXT NOT NULL,
        plan TEXT NOT NULL,
        stripe_session_id TEXT,
        status TEXT DEFAULT 'pending',
        recovery_sent_at TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS diagnosis_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id INTEGER NOT NULL,
        helpful INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS recovery_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        plan TEXT NOT NULL,
        stage INTEGER NOT NULL DEFAULT 1,
        send_at TEXT NOT NULL,
        sent INTEGER DEFAULT 0,
        sent_at TEXT,
        stripe_session_id TEXT,
        created_at TEXT NOT NULL,
        unsubscribed INTEGER DEFAULT 0
    )""")
    db.commit()
    return db


# ── Routes ──────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    equipment = _load_equipment()
    return templates.TemplateResponse("diagnose.html", {
        "request": request,
        "equipment": equipment,
    })


@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(request: Request, slug: str):
    """Serve blog posts from templates/blog/ directory."""
    safe_slug = slug.replace("..", "").replace("/", "")
    template_path = f"blog/{safe_slug}.html"
    try:
        return templates.TemplateResponse(template_path, {"request": request})
    except Exception:
        return HTMLResponse("<h1>Post not found</h1>", status_code=404)


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    return templates.TemplateResponse("pricing.html", {"request": request})


@app.get("/api/analytics/hit")
async def analytics_hit(request: Request, p: str = "/", r: str = ""):
    """Self-hosted analytics pixel. Logs page view to local JSONL."""
    try:
        log_path = LOGS_PATH / "analytics.jsonl"
        entry = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "page": p[:200],
            "referrer": r[:500],
            "ip": request.client.host if request.client else "",
            "ua": (request.headers.get("user-agent") or "")[:200],
        })
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass
    return JSONResponse({"ok": True}, status_code=204)


@app.get("/store", response_class=HTMLResponse)
async def store_page(request: Request):
    return templates.TemplateResponse("store.html", {"request": request})


# ── Comparison pages (SEO) ─────────────────────────────────────────────────

COMPARE_PAGES = {
    "maintainx": {
        "template": "compare/maintainx.html",
        "title": "RepairXpert vs MaintainX",
    },
    "servicetitan": {
        "template": "compare/servicetitan.html",
        "title": "RepairXpert vs ServiceTitan",
    },
    "upkeep": {
        "template": "compare/upkeep.html",
        "title": "RepairXpert vs UpKeep",
    },
    "emaint": {
        "template": "compare/emaint.html",
        "title": "RepairXpert vs eMaint",
    },
    "limble": {
        "template": "compare/limble.html",
        "title": "RepairXpert vs Limble CMMS",
    },
    "plcai": {
        "template": "compare/plcai.html",
        "title": "RepairXpert vs PLC AI",
    },
}


@app.get("/compare", response_class=HTMLResponse)
async def compare_index(request: Request):
    return templates.TemplateResponse("compare/index.html", {"request": request})


@app.get("/compare/{competitor}", response_class=HTMLResponse)
async def compare_page(request: Request, competitor: str):
    page = COMPARE_PAGES.get(competitor.lower())
    if not page:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return templates.TemplateResponse(page["template"], {"request": request})


@app.post("/api/checkout")
async def create_checkout_session(request: Request):
    """Create a Stripe Checkout Session and return the redirect URL."""
    if not _stripe_available:
        return JSONResponse(
            {"error": "Payments are not configured. Set STRIPE_SECRET_KEY in your environment."},
            status_code=503,
        )

    body = await request.json()
    plan = body.get("plan", "")
    email = body.get("email", "").strip()

    if plan not in STRIPE_PRICE_IDS:
        return JSONResponse({"error": f"Unknown plan: {plan}"}, status_code=400)

    price_id = STRIPE_PRICE_IDS[plan]
    if not price_id:
        return JSONResponse(
            {"error": f"Stripe Price ID not configured for '{plan}'. Set STRIPE_PRICE_ID_{plan.upper()} in env."},
            status_code=503,
        )

    base_url = str(request.base_url).rstrip("/")

    try:
        session_params = {
            "mode": "subscription",
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{base_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base_url}/checkout/cancel",
        }
        if email:
            session_params["customer_email"] = email

        session = stripe.checkout.Session.create(**session_params)

        # Log lead to SQLite for recovery
        if email:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO checkout_leads (created_at, email, plan, stripe_session_id) VALUES (?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), email, plan, session.id),
                )
                db.commit()
                db.close()
            except Exception:
                pass  # Don't block checkout on logging failure

        return JSONResponse({"checkout_url": session.url})
    except stripe.error.StripeError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/checkout/success", response_class=HTMLResponse)
async def checkout_success(request: Request):
    return templates.TemplateResponse("checkout_success.html", {"request": request})


@app.get("/checkout/cancel", response_class=HTMLResponse)
async def checkout_cancel(request: Request):
    return templates.TemplateResponse("checkout_cancel.html", {"request": request})


# ── Stripe Webhook ────────────────────────────────────────────────────────────


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for cart recovery and conversion tracking."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not (STRIPE_WEBHOOK_SECRET and _stripe_available):
        # SECURITY: never accept unsigned events. Code scout 2026-04-07 flagged
        # this branch as a free-access bypass when STRIPE_WEBHOOK_SECRET is unset.
        return JSONResponse(
            {"error": "Webhook verification not configured"}, status_code=503
        )
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    event_type = event.get("type", "")
    data_obj = event.get("data", {}).get("object", {})

    _log_stripe_event(event_type, data_obj)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data_obj)
    elif event_type == "checkout.session.expired":
        _handle_checkout_expired(data_obj)

    return JSONResponse({"status": "ok"})


@app.post("/api/checkout/recover")
async def recover_checkout(request: Request):
    """Email capture on cancel page — creates a new checkout session and sends recovery email."""
    body = await request.json()
    email = body.get("email", "").strip()
    plan = body.get("plan", "pro")

    if not email:
        return JSONResponse({"error": "Email required"}, status_code=400)

    # Log the lead
    try:
        db = get_db()
        db.execute(
            "INSERT INTO checkout_leads (created_at, email, plan, status) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), email, plan, "recover_requested"),
        )
        db.commit()
        db.close()
    except Exception:
        pass

    # Send recovery email with fresh checkout link
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://repairxpertai.com")
    _send_recovery_email(email, plan, base_url, stage=1)

    return JSONResponse({"status": "ok", "message": "We'll send you a link to complete your subscription."})


def _handle_checkout_completed(session: dict):
    """Mark lead as converted and cancel any pending recovery emails."""
    email = session.get("customer_email", "") or session.get("customer_details", {}).get("email", "")
    if email:
        try:
            db = get_db()
            db.execute("UPDATE checkout_leads SET status='converted' WHERE email=? AND status='pending'", (email,))
            # Cancel any unsent recovery emails — they converted
            db.execute(
                "UPDATE recovery_queue SET sent=1, sent_at=? WHERE email=? AND sent=0",
                (datetime.now(timezone.utc).isoformat(), email),
            )
            db.commit()
            db.close()
            _log_stripe_event("recovery_cancelled_converted", {"email": email})
        except Exception:
            pass


def _handle_checkout_expired(session: dict):
    """Queue 3-email recovery sequence for expired checkout sessions."""
    email = session.get("customer_email", "")
    if not email:
        return

    # Skip test accounts
    if email.lower() in ("ericwestmail@gmail.com", "test@test.com"):
        return

    now = datetime.now(timezone.utc)

    try:
        db = get_db()
        # Check if we already have a recovery queue for this email in the last 7 days
        recent = db.execute(
            "SELECT id FROM recovery_queue WHERE email=? AND created_at > ? LIMIT 1",
            (email, (now - timedelta(days=7)).isoformat()),
        ).fetchone()
        if recent:
            db.close()
            _log_stripe_event("recovery_skipped_duplicate", {"email": email})
            return

        # Check if unsubscribed
        unsub = db.execute(
            "SELECT id FROM recovery_queue WHERE email=? AND unsubscribed=1 LIMIT 1",
            (email,),
        ).fetchone()
        if unsub:
            db.close()
            _log_stripe_event("recovery_skipped_unsubscribed", {"email": email})
            return

        # Mark lead as expired
        db.execute(
            "UPDATE checkout_leads SET status='expired', recovery_sent_at=? WHERE email=? AND status='pending'",
            (now.isoformat(), email),
        )

        # Determine plan from amount or line items
        plan = "pro"
        amount_total = session.get("amount_total", 0)
        if amount_total and amount_total >= 4900:
            plan = "enterprise"
        else:
            line_items = session.get("line_items", {}).get("data", [])
            if line_items:
                price_id = line_items[0].get("price", {}).get("id", "")
                if price_id == STRIPE_PRICE_IDS.get("enterprise"):
                    plan = "enterprise"

        stripe_session_id = session.get("id", "")

        # Queue 3 emails: 1h, 24h, 72h
        for stage, hours in [(1, 1), (2, 24), (3, 72)]:
            send_at = (now + timedelta(hours=hours)).isoformat()
            db.execute(
                "INSERT INTO recovery_queue (email, plan, stage, send_at, stripe_session_id, created_at) VALUES (?,?,?,?,?,?)",
                (email, plan, stage, send_at, stripe_session_id, now.isoformat()),
            )

        db.commit()
        db.close()
        _log_stripe_event("recovery_queued", {"email": email, "plan": plan, "stages": "1,2,3"})
    except Exception as e:
        _log_stripe_event("recovery_queue_error", {"email": email, "error": str(e)})


def _send_recovery_email(email: str, plan: str, base_url: str, stage: int = 1):
    """Send staged abandoned cart recovery email via Resend.

    Stage 1 (1h):  "Still thinking about it?" — reminder, remove friction
    Stage 2 (24h): "Your diagnostic tool is waiting" — value prop, use cases
    Stage 3 (72h): "Last chance" — urgency, money-back guarantee
    """
    if not RESEND_API_KEY:
        _log_stripe_event("recovery_email_skipped", {"email": email, "reason": "no_resend_key"})
        return False

    plan_name = "Enterprise" if plan == "enterprise" else "Pro"
    plan_price = "$99" if plan == "enterprise" else "$19"
    unsub_url = f"{base_url}/api/recovery/unsubscribe?email={email}"
    pricing_url = f"{base_url}/pricing"

    # ── Stage 1: "Still thinking about it?" (1 hour) ─────────────────────────
    if stage == 1:
        subject = f"Still thinking about the {plan_name} plan?"
        html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">Still thinking about it?</h2>
<p>You started checking out the <strong>{plan_name}</strong> plan ({plan_price}/mo) but didn't finish. No worries — your spot is still available.</p>
<p style="margin:1.5rem 0">Quick reminder of what you get:</p>
<ul style="color:#c9d1d9;line-height:1.8">
<li>Unlimited AI fault diagnoses</li>
<li>Photo analysis of equipment and panels</li>
<li>313 fault codes across 7 equipment categories</li>
<li>Parts recommendations with real-time pricing</li>
{"<li>REST API access + team features</li>" if plan == "enterprise" else ""}
</ul>
<p style="margin:1.5rem 0">
<a href="{pricing_url}" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">Complete Your Subscription</a>
</p>
<p style="color:#8b949e;font-size:0.85rem">If something went wrong during checkout, just reply to this email.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians<br>
<a href="{unsub_url}" style="color:#8b949e">Unsubscribe from recovery emails</a></p>
</div>"""

    # ── Stage 2: "Your diagnostic tool is waiting" (24 hours) ─────────────────
    elif stage == 2:
        subject = f"Your {plan_name} diagnostic tool is waiting"
        html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">Your diagnostic tool is waiting</h2>
<p>Yesterday you looked at the <strong>{plan_name}</strong> plan ({plan_price}/mo).</p>
<p style="margin:1rem 0">Here's what field techs use it for:</p>
<ul style="color:#c9d1d9;line-height:1.8">
<li>Pull up a fault code mid-shift — get probable causes + fix steps in 30 seconds</li>
<li>Snap a photo of a panel — AI identifies the issue</li>
<li>Find the right replacement part with SKU and pricing</li>
<li>Works on your phone, even on a ladder</li>
</ul>
<p style="margin:1.5rem 0">
<a href="{pricing_url}" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">Pick Up Where You Left Off</a>
</p>
<p style="color:#8b949e;font-size:0.85rem">3 free diagnoses/day on the free tier if you want to test first. Cancel anytime. No contracts.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians<br>
<a href="{unsub_url}" style="color:#8b949e">Unsubscribe from recovery emails</a></p>
</div>"""

    # ── Stage 3: "Last chance" (72 hours) ─────────────────────────────────────
    else:
        subject = f"Last chance: {plan_name} plan — 7-day money-back guarantee"
        html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">Last chance — then we'll stop emailing</h2>
<p>This is the last email about this, promise.</p>
<p style="margin:1rem 0">If the <strong>{plan_name}</strong> plan doesn't pay for itself in the first week, we'll refund you immediately. No forms, no hoops.</p>
<p>That's <strong>{plan_price}/mo</strong> to save hours of manual troubleshooting per week.</p>
<p style="margin:1.5rem 0">
<a href="{pricing_url}" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">Start Your Subscription</a>
</p>
<p style="color:#8b949e;font-size:0.85rem">If it's not the right fit, no hard feelings. The free tier (3 diagnoses/day) is always there.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians<br>
<a href="{unsub_url}" style="color:#8b949e">Unsubscribe from recovery emails</a></p>
</div>"""

    try:
        import urllib.request
        payload = json.dumps({
            "from": "RepairXpert AI <hello@repairxpertai.com>",
            "to": [email],
            "reply_to": "ericwestmail@gmail.com",
            "subject": subject,
            "html": html_body,
        }).encode()

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {RESEND_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            _log_stripe_event("recovery_email_sent", {"email": email, "plan": plan, "stage": stage})
            return True
    except Exception as e:
        _log_stripe_event("recovery_email_failed", {"email": email, "stage": stage, "error": str(e)})
        return False


def _log_stripe_event(event_type: str, data: dict):
    """Append Stripe/recovery event to JSONL log."""
    try:
        allowed = (
            "id", "customer_email", "email", "plan", "status",
            "amount_total", "currency", "reason", "error", "stage", "stages",
        )
        log_entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "data": {k: v for k, v in data.items() if k in allowed},
        })
        with open(LOGS_PATH / "stripe_events.jsonl", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception:
        pass


# ── Cart Recovery Processing ─────────────────────────────────────────────────


@app.post("/api/recovery/process")
async def process_recovery_queue(request: Request):
    """Process due recovery emails from the queue. Hit this hourly via UNO/cron.

    Security: requires X-Recovery-Key header matching STRIPE_WEBHOOK_SECRET
    to prevent unauthorized triggering.
    """
    auth_key = request.headers.get("x-recovery-key", "")
    if not auth_key or auth_key != STRIPE_WEBHOOK_SECRET:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    now = datetime.now(timezone.utc)
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://indautomation.onrender.com")
    sent_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        db = get_db()

        # Get all due, unsent, non-unsubscribed emails
        rows = db.execute(
            "SELECT id, email, plan, stage FROM recovery_queue "
            "WHERE sent=0 AND unsubscribed=0 AND send_at <= ? "
            "ORDER BY send_at ASC LIMIT 50",
            (now.isoformat(),),
        ).fetchall()

        for row in rows:
            email = row["email"]
            plan = row["plan"]
            stage = row["stage"]
            queue_id = row["id"]

            # Check if this email converted (completed checkout) since we queued
            converted = db.execute(
                "SELECT id FROM checkout_leads WHERE email=? AND status='converted' LIMIT 1",
                (email,),
            ).fetchone()
            if converted:
                # Mark remaining queue items as skipped
                db.execute(
                    "UPDATE recovery_queue SET sent=1, sent_at=? WHERE email=? AND sent=0",
                    (now.isoformat(), email),
                )
                skipped_count += 1
                _log_stripe_event("recovery_skipped_converted", {"email": email, "stage": stage})
                continue

            # Check if earlier stages for same email were unsubscribed
            unsub = db.execute(
                "SELECT id FROM recovery_queue WHERE email=? AND unsubscribed=1 LIMIT 1",
                (email,),
            ).fetchone()
            if unsub:
                db.execute(
                    "UPDATE recovery_queue SET sent=1, sent_at=? WHERE email=? AND sent=0",
                    (now.isoformat(), email),
                )
                skipped_count += 1
                continue

            # Send the email
            success = _send_recovery_email(email, plan, base_url, stage=stage)
            if success:
                db.execute(
                    "UPDATE recovery_queue SET sent=1, sent_at=? WHERE id=?",
                    (now.isoformat(), queue_id),
                )
                sent_count += 1
            else:
                failed_count += 1

        db.commit()
        db.close()
    except Exception as e:
        _log_stripe_event("recovery_process_error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({
        "status": "ok",
        "processed_at": now.isoformat(),
        "sent": sent_count,
        "skipped": skipped_count,
        "failed": failed_count,
    })


@app.get("/api/recovery/unsubscribe")
async def recovery_unsubscribe(request: Request, email: str = ""):
    """Unsubscribe an email from recovery sequence. Returns simple HTML confirmation."""
    if not email or "@" not in email:
        return HTMLResponse("<h1>Invalid email</h1>", status_code=400)

    try:
        db = get_db()
        db.execute(
            "UPDATE recovery_queue SET unsubscribed=1 WHERE email=?",
            (email.strip().lower(),),
        )
        db.commit()
        db.close()
        _log_stripe_event("recovery_unsubscribed", {"email": email})
    except Exception:
        pass

    return HTMLResponse(
        '<div style="font-family:-apple-system,sans-serif;max-width:480px;margin:4rem auto;text-align:center;color:#c9d1d9;background:#0d1117;padding:2rem;border-radius:8px">'
        '<h2 style="color:#f78166">Unsubscribed</h2>'
        "<p>You won't receive any more recovery emails from RepairXpert.</p>"
        '<p style="color:#8b949e;font-size:0.85rem;margin-top:1.5rem">'
        'You can still use the <a href="https://indautomation.onrender.com/diagnose" style="color:#58a6ff">free diagnostic tool</a> anytime.</p>'
        "</div>"
    )


@app.get("/api/recovery/stats")
async def recovery_stats(request: Request):
    """Return cart recovery funnel stats. Requires auth header."""
    auth_key = request.headers.get("x-recovery-key", "")
    if not auth_key or auth_key != STRIPE_WEBHOOK_SECRET:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        db = get_db()
        total = db.execute("SELECT COUNT(*) as c FROM recovery_queue").fetchone()["c"]
        sent = db.execute("SELECT COUNT(*) as c FROM recovery_queue WHERE sent=1 AND unsubscribed=0").fetchone()["c"]
        pending = db.execute("SELECT COUNT(*) as c FROM recovery_queue WHERE sent=0 AND unsubscribed=0").fetchone()["c"]
        unsubscribed = db.execute("SELECT COUNT(DISTINCT email) as c FROM recovery_queue WHERE unsubscribed=1").fetchone()["c"]

        # Per-stage breakdown
        stages = {}
        for stage in [1, 2, 3]:
            row = db.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN sent=1 THEN 1 ELSE 0 END) as sent_count "
                "FROM recovery_queue WHERE stage=?",
                (stage,),
            ).fetchone()
            stages[f"stage_{stage}"] = {
                "total": row["total"],
                "sent": row["sent_count"] or 0,
            }

        # Unique emails in recovery
        unique_emails = db.execute("SELECT COUNT(DISTINCT email) as c FROM recovery_queue").fetchone()["c"]

        # Converted after recovery
        converted = db.execute(
            "SELECT COUNT(DISTINCT rq.email) as c FROM recovery_queue rq "
            "INNER JOIN checkout_leads cl ON rq.email = cl.email "
            "WHERE cl.status = 'converted'",
        ).fetchone()["c"]

        db.close()
        return JSONResponse({
            "total_queued": total,
            "sent": sent,
            "pending": pending,
            "unsubscribed": unsubscribed,
            "unique_emails": unique_emails,
            "converted_after_recovery": converted,
            "recovery_rate": round(converted / unique_emails * 100, 1) if unique_emails > 0 else 0,
            "stages": stages,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/lead")
async def capture_lead(request: Request):
    """Capture a lead: validate email+name, create Stripe customer, send welcome email, log for follow-up."""
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()

    if not email or "@" not in email:
        return JSONResponse({"error": "Valid email required"}, status_code=400)
    if not name:
        return JSONResponse({"error": "Name required"}, status_code=400)

    now = datetime.now(timezone.utc).isoformat()

    # Create Stripe customer
    stripe_customer_id = None
    if _stripe_available:
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"source": "lead_capture", "captured_at": now},
            )
            stripe_customer_id = customer.id
        except Exception as e:
            _log_stripe_event("lead_stripe_error", {"email": email, "error": str(e)})

    # Log lead to SQLite for follow-up sequence
    try:
        db = get_db()
        db.execute(
            "INSERT INTO checkout_leads (created_at, email, plan, stripe_session_id, status) VALUES (?,?,?,?,?)",
            (now, email, "lead", stripe_customer_id, "lead_captured"),
        )
        db.commit()
        db.close()
    except Exception:
        pass

    # Send welcome email via Resend
    if RESEND_API_KEY:
        base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://indautomation.onrender.com")
        html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">Welcome to RepairXpert, {name}</h2>
<p>You're on the list. We help industrial field techs diagnose faults faster with AI-powered fault codes, wiring diagrams, and parts recommendations.</p>
<p style="margin:1.5rem 0">Ready to try it?</p>
<a href="{base_url}/diagnose" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">Run a Free Diagnosis</a>
<p style="margin-top:1.5rem;color:#8b949e;font-size:0.85rem">313+ fault codes. Allen-Bradley, Siemens, Fanuc and more. No contracts.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians</p>
</div>"""
        try:
            import urllib.request as _ureq
            payload = json.dumps({
                "from": "RepairXpert <hello@repairxpertai.com>",
                "to": [email],
                "reply_to": "ericwestmail@gmail.com",
                "subject": "Welcome to RepairXpert — your free diagnosis is ready",
                "html": html_body,
            }).encode()
            req = _ureq.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {RESEND_API_KEY}"},
            )
            with _ureq.urlopen(req, timeout=10):
                pass
            _log_stripe_event("lead_welcome_sent", {"email": email})
        except Exception as e:
            _log_stripe_event("lead_welcome_failed", {"email": email, "error": str(e)})

    _log_stripe_event("lead_captured", {"email": email, "plan": "lead", "id": stripe_customer_id or ""})
    return JSONResponse({"status": "ok", "message": "Lead captured", "stripe_customer_id": stripe_customer_id})


@app.post("/diagnose", response_class=HTMLResponse)
async def diagnose_form(
    request: Request,
    equipment_type: str = Form(""),
    fault_code: str = Form(""),
    symptoms: str = Form(""),
    photo: UploadFile | None = File(None),
):
    """HTML form submission — renders diagnose.html with results."""
    photo_result = None
    if photo and photo.filename:
        photo_bytes = await photo.read()
        if photo_bytes:
            photo_result = analyze_photo(photo_bytes, equipment_type, fault_code, CONFIG)

    result = diagnose_fault(equipment_type, fault_code, symptoms, photo_result, CONFIG)
    diagnosis_id = _save_diagnosis(result, equipment_type, fault_code, symptoms, photo_result)

    return templates.TemplateResponse("diagnose.html", {
        "request": request,
        "result": result,
        "diagnosis_id": diagnosis_id,
    })


@app.post("/diagnose/photo")
async def diagnose_photo_api(
    equipment_type: str = Form(""),
    fault_code: str = Form(""),
    photo: UploadFile = File(...),
):
    """Photo-only diagnosis endpoint — returns JSON."""
    photo_bytes = await photo.read()
    if not photo_bytes:
        return JSONResponse({"error": "No photo data received"}, status_code=400)

    photo_result = analyze_photo(photo_bytes, equipment_type, fault_code, CONFIG)

    # Also run fault diagnosis with photo insight
    result = diagnose_fault(equipment_type, fault_code, "", photo_result, CONFIG)
    _save_diagnosis(result, equipment_type, fault_code, "(photo only)", photo_result)

    return JSONResponse(result)


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Render history page with past diagnoses."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM diagnoses ORDER BY id DESC LIMIT 50"
    ).fetchall()
    db.close()
    entries = []
    for r in rows:
        entry = dict(r)
        # Parse JSON fields for template
        try:
            entry["diagnosis_list"] = json.loads(entry.get("diagnosis") or "[]")
        except (json.JSONDecodeError, TypeError):
            entry["diagnosis_list"] = []
        try:
            entry["fix_steps_list"] = json.loads(entry.get("fix_steps") or "[]")
        except (json.JSONDecodeError, TypeError):
            entry["fix_steps_list"] = []
        entries.append(entry)
    # Feedback satisfaction stats
    db2 = get_db()
    fb_row = db2.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN helpful=1 THEN 1 ELSE 0 END) as helpful_count
        FROM diagnosis_feedback
    """).fetchone()
    db2.close()
    fb_total = fb_row["total"] if fb_row else 0
    fb_helpful = fb_row["helpful_count"] if fb_row else 0
    satisfaction_pct = round(fb_helpful / fb_total * 100, 1) if fb_total > 0 else 0

    return templates.TemplateResponse("history.html", {
        "request": request,
        "entries": entries,
        "feedback_total": fb_total,
        "feedback_helpful": fb_helpful,
        "satisfaction_pct": satisfaction_pct,
    })


@app.get("/faults", response_class=HTMLResponse)
async def fault_index(request: Request):
    """SEO index page listing every fault code with links to detail pages."""
    faults = load_fault_db()
    # Group by equipment_type for organized display
    grouped: dict[str, list[dict]] = {}
    for f in faults:
        eq = f.get("equipment_type", "general")
        grouped.setdefault(eq, []).append(f)
    return templates.TemplateResponse("fault_index.html", {
        "request": request,
        "faults": faults,
        "grouped": grouped,
        "total": len(faults),
    })


# ── SEO Fault Code Landing Pages ─────────────────────────────────────────────

def _filter_faults_by_keywords(faults: list[dict], keywords: list[str]) -> list[dict]:
    """Filter fault DB entries whose code or equipment_type matches any keyword."""
    results = []
    for f in faults:
        code = f.get("code", "").lower()
        eq = f.get("equipment_type", "").lower()
        name = f.get("name", "").lower()
        tags = " ".join(f.get("tags", [])).lower() if f.get("tags") else ""
        searchable = f"{code} {eq} {name} {tags}"
        if any(kw in searchable for kw in keywords):
            results.append(f)
    return results


@app.get("/faults/allen-bradley", response_class=HTMLResponse)
async def faults_allen_bradley(request: Request):
    """SEO landing page: Allen-Bradley fault codes (2400 searches/mo)."""
    faults = load_fault_db()
    ab_keywords = ["allen-bradley", "allen_bradley", "ab-", "controllogix", "compactlogix",
                    "guardlogix", "powerflex", "guardmaster", "cr30", "enet", "rockwell"]
    ab_faults = _filter_faults_by_keywords(faults, ab_keywords)
    # Sub-categorize by equipment_type
    ab_categories: dict[str, list[dict]] = {}
    for f in ab_faults:
        eq = f.get("equipment_type", "general")
        ab_categories.setdefault(eq, []).append(f)
    return templates.TemplateResponse("faults/allen-bradley.html", {
        "request": request,
        "ab_faults": ab_faults,
        "ab_categories": ab_categories,
        "ab_count": len(ab_faults),
        "total": len(faults),
    })


@app.get("/faults/vfd", response_class=HTMLResponse)
async def faults_vfd(request: Request):
    """SEO landing page: VFD fault codes (1600 searches/mo)."""
    faults = load_fault_db()
    vfd_keywords = ["vfd", "variable frequency", "powerflex", "drive", "overcurrent",
                     "overvoltage", "ab-vfd", "vfd-"]
    vfd_faults = _filter_faults_by_keywords(faults, vfd_keywords)
    return templates.TemplateResponse("faults/vfd.html", {
        "request": request,
        "vfd_faults": vfd_faults,
        "vfd_count": len(vfd_faults),
        "total": len(faults),
    })


@app.get("/faults/plc-errors", response_class=HTMLResponse)
async def faults_plc_errors(request: Request):
    """SEO landing page: PLC error code lookup (1900 searches/mo)."""
    faults = load_fault_db()
    plc_keywords = ["plc", "controllogix", "compactlogix", "guardlogix", "ab-plc",
                     "major fault", "minor fault", "watchdog", "program fault"]
    plc_faults = _filter_faults_by_keywords(faults, plc_keywords)
    # Sub-categorize
    plc_categories: dict[str, list[dict]] = {}
    for f in plc_faults:
        eq = f.get("equipment_type", "general")
        plc_categories.setdefault(eq, []).append(f)
    return templates.TemplateResponse("faults/plc-errors.html", {
        "request": request,
        "plc_faults": plc_faults,
        "plc_categories": plc_categories,
        "plc_count": len(plc_faults),
        "total": len(faults),
    })


@app.get("/api/faults-data")
async def faults_data():
    """Raw fault database as JSON — cached by service worker for offline use."""
    faults = load_fault_db()
    return JSONResponse(
        content={"faults": faults, "total": len(faults)},
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/fault/{code}", response_class=HTMLResponse)
async def fault_detail(request: Request, code: str):
    """SEO-optimized detail page for a single fault code."""
    faults = load_fault_db()
    entry = None
    for f in faults:
        if f.get("code", "").lower() == code.lower():
            entry = f
            break
    if not entry:
        # Try partial/slug match (e.g. AB-PF-F004)
        for f in faults:
            if code.lower() in f.get("code", "").lower():
                entry = f
                break
    if not entry:
        return templates.TemplateResponse("fault_detail.html", {
            "request": request,
            "entry": None,
            "code": code,
            "parts": [],
        })
    # Load suggested parts for this fault category
    parts = []
    parts_category = entry.get("parts_category", "")
    if parts_category:
        parts = get_parts_for_category(parts_category)
    return templates.TemplateResponse("fault_detail.html", {
        "request": request,
        "entry": entry,
        "code": entry.get("code", code),
        "parts": parts,
        "parts_category": parts_category,
    })


# ── OBD-II Scanner ────────────────────────────────────────────────────────────
_auto_dtc_cache = None

def _load_auto_dtcs():
    global _auto_dtc_cache
    if _auto_dtc_cache is not None:
        return _auto_dtc_cache
    path = ROOT / "indauto" / "fault_db" / "automotive_dtcs.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        _auto_dtc_cache = data.get("faults", [])
    else:
        _auto_dtc_cache = []
    return _auto_dtc_cache


@app.get("/obd", response_class=HTMLResponse)
async def obd_page(request: Request):
    """OBD-II scanner page — vehicle diagnostics for field techs."""
    return templates.TemplateResponse("obd.html", {"request": request})


@app.post("/api/obd/scan")
async def api_obd_scan(request: Request):
    """Trigger OBD-II DTC scan (mock mode). Returns DTCs + live sensor snapshot."""
    import random
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    action = body.get("action", "scan")

    if action == "clear":
        return JSONResponse({"message": "DTCs cleared successfully. (Mock mode — no vehicle connected.)", "status": "ok"})

    # Mock DTCs
    mock_dtcs = [
        {"code": "P0300", "description": "Random/Multiple Cylinder Misfire Detected", "status": "confirmed", "severity": "high"},
        {"code": "P0171", "description": "System Too Lean (Bank 1)", "status": "confirmed", "severity": "medium"},
        {"code": "P0420", "description": "Catalyst System Efficiency Below Threshold (Bank 1)", "status": "pending", "severity": "medium"},
    ]
    # Mock live data
    live_data = {
        "rpm": {"value": 780 + random.randint(-30, 30), "unit": "RPM", "description": "Engine RPM"},
        "speed": {"value": 0, "unit": "mph", "description": "Vehicle Speed"},
        "coolant_temp": {"value": 195 + random.randint(-3, 3), "unit": "F", "description": "Coolant Temp"},
        "engine_load": {"value": round(28.6 + random.uniform(-2, 2), 1), "unit": "%", "description": "Engine Load"},
        "throttle_pos": {"value": round(15.7 + random.uniform(-1, 1), 1), "unit": "%", "description": "Throttle Position"},
        "maf": {"value": round(3.8 + random.uniform(-0.3, 0.3), 1), "unit": "g/s", "description": "Mass Air Flow"},
        "short_fuel_trim_1": {"value": round(2.3 + random.uniform(-1, 1), 1), "unit": "%", "description": "STFT Bank 1"},
        "long_fuel_trim_1": {"value": round(4.7 + random.uniform(-0.5, 0.5), 1), "unit": "%", "description": "LTFT Bank 1"},
        "fuel_pressure": {"value": 58 + random.randint(-2, 2), "unit": "PSI", "description": "Fuel Pressure"},
        "timing_advance": {"value": round(12.5 + random.uniform(-1, 1), 1), "unit": "deg", "description": "Timing Advance"},
        "o2_voltage_b1s1": {"value": round(0.45 + random.uniform(-0.2, 0.2), 2), "unit": "V", "description": "O2 B1S1"},
        "control_module_voltage": {"value": round(14.1 + random.uniform(-0.2, 0.2), 1), "unit": "V", "description": "System Voltage"},
        "fuel_level": {"value": 62, "unit": "%", "description": "Fuel Level"},
        "ambient_temp": {"value": 78 + random.randint(-2, 2), "unit": "F", "description": "Ambient Temp"},
    }

    if body.get("live_only"):
        return JSONResponse({"live_data": live_data, "mode": "mock"})

    return JSONResponse({"dtcs": mock_dtcs, "live_data": live_data, "mode": "mock"})


@app.get("/api/obd/dtc/{code}")
async def api_obd_dtc_lookup(code: str):
    """Look up a single automotive DTC from the database."""
    code_upper = code.strip().upper()
    for entry in _load_auto_dtcs():
        if entry.get("code", "").upper() == code_upper:
            return JSONResponse(entry)
    return JSONResponse({"error": f"DTC '{code_upper}' not found in database"}, status_code=404)


@app.get("/api/obd/search")
async def api_obd_search(q: str = ""):
    """Search automotive DTCs by keyword."""
    if not q or len(q) < 2:
        return JSONResponse({"error": "Query must be at least 2 characters", "results": []}, status_code=400)
    q_lower = q.lower()
    results = []
    seen_codes = set()
    for entry in _load_auto_dtcs():
        code = entry.get("code", "")
        if code in seen_codes:
            continue
        searchable = f"{code} {entry.get('name', '')} {entry.get('equipment_type', '')} {' '.join(entry.get('probable_causes', []))} {' '.join(entry.get('tags', []))}".lower()
        if q_lower in searchable:
            results.append({"code": code, "name": entry["name"], "severity": entry.get("severity", "medium"), "equipment_type": entry.get("equipment_type", "engine")})
            seen_codes.add(code)
        if len(results) >= 25:
            break
    return JSONResponse({"query": q, "count": len(results), "results": results})


@app.get("/vin", response_class=HTMLResponse)
async def vin_page(request: Request):
    """VIN decoder page — free tool for field techs."""
    return templates.TemplateResponse("vin.html", {"request": request, "result": None})


@app.post("/vin", response_class=HTMLResponse)
async def vin_lookup(request: Request, vin: str = Form("")):
    """Decode a VIN using the free NHTSA vPIC API."""
    result = None
    error = None
    if vin and len(vin) >= 11:
        import urllib.request
        import urllib.error
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RepairXpert/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("Results"):
                    raw = data["Results"][0]
                    result = {k: v for k, v in raw.items() if v and v.strip()}
        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            error = str(e)
    elif vin:
        error = "VIN must be at least 11 characters"
    return templates.TemplateResponse("vin.html", {
        "request": request,
        "result": result,
        "vin": vin,
        "error": error,
    })


@app.get("/api/vin/{vin}")
async def api_vin_decode(vin: str):
    """JSON VIN decode endpoint for programmatic access."""
    import urllib.request
    import urllib.error
    if len(vin) < 11:
        return JSONResponse({"error": "VIN must be at least 11 characters"}, status_code=400)
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RepairXpert/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("Results"):
                raw = data["Results"][0]
                return JSONResponse({k: v for k, v in raw.items() if v and v.strip()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return JSONResponse({"error": "No results"}, status_code=404)


@app.get("/sitemap.xml")
async def sitemap(request: Request):
    """Dynamic XML sitemap for SEO — lists all fault code pages."""
    faults = load_fault_db()
    base = str(request.base_url).rstrip("/")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        f'<url><loc>{base}/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>',
        f'<url><loc>{base}/faults</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'<url><loc>{base}/faults/allen-bradley</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'<url><loc>{base}/faults/vfd</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'<url><loc>{base}/faults/plc-errors</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'<url><loc>{base}/pricing</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/vin</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/obd</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'<url><loc>{base}/compare</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/maintainx</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/servicetitan</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/upkeep</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/emaint</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/limble</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
    ]
    for f in faults:
        code = f.get("code", "")
        urls.append(f'<url><loc>{base}/fault/{code}</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"
    from starlette.responses import Response
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
async def robots(request: Request):
    base = str(request.base_url).rstrip("/")
    txt = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    from starlette.responses import Response
    return Response(content=txt, media_type="text/plain")


# ── IndexNow verification key ──────────────────────────────────────────────────
INDEXNOW_KEY = "fe1a967cb18a4679a754c625d57b7a6d"


@app.get(f"/{INDEXNOW_KEY}.txt")
async def indexnow_key_file():
    from starlette.responses import Response
    return Response(content=INDEXNOW_KEY, media_type="text/plain")


@app.get("/api/revenue-loop")
async def revenue_loop_status():
    """View 24/7 revenue loop status and recent log."""
    return {"status": "running" if _revenue_thread and _revenue_thread.is_alive() else "stopped",
            "log": get_revenue_log()}


@app.get("/api/health")
async def health():
    fault_count = len(load_fault_db())
    equipment = _load_equipment()

    # Count total diagnoses for uptime stats
    db_exists = DB_PATH.exists()
    total_diagnoses = 0
    last_diagnosis = None
    if db_exists:
        try:
            db = get_db()
            row = db.execute("SELECT COUNT(*) as cnt, MAX(created_at) as last_ts FROM diagnoses").fetchone()
            total_diagnoses = row["cnt"] if row else 0
            last_diagnosis = row["last_ts"] if row else None
            db.close()
        except Exception:
            pass

    # Check LM Studio connectivity
    lm_status = "unknown"
    try:
        import urllib.request
        base_url = CONFIG.get("lm_studio", {}).get("base_url", "http://127.0.0.1:1234/v1")
        req = urllib.request.Request(f"{base_url}/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as res:
            lm_status = "connected"
    except Exception:
        lm_status = "unavailable"

    return {
        "status": "ok",
        "service": "RepairXpert IndAutomation",
        "version": app.version,
        "port": CONFIG["app"]["port"],
        "fault_codes_loaded": fault_count,
        "equipment_profiles": len(equipment),
        "total_diagnoses": total_diagnoses,
        "last_diagnosis_at": last_diagnosis,
        "lm_studio": lm_status,
        "database": "ok" if db_exists else "new",
    }


# ── Admin Dashboard ──────────────────────────────────────────────────────────

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Real-time admin dashboard with diagnoses, revenue, health."""
    import urllib.request as _ur

    # Stats from DB
    total_diagnoses = 0
    top_faults = []
    recent = []
    try:
        db = get_db()
        row = db.execute("SELECT COUNT(*) as cnt FROM diagnoses").fetchone()
        total_diagnoses = row["cnt"] if row else 0

        # Top fault codes
        rows = db.execute(
            "SELECT fault_code, fault_name, COUNT(*) as cnt FROM diagnoses "
            "GROUP BY fault_code ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        top_faults = [{"code": r["fault_code"], "name": r["fault_name"] or "Unknown", "count": r["cnt"]} for r in rows]

        # Recent diagnoses
        rows = db.execute(
            "SELECT created_at, fault_code, equipment_type, source, confidence "
            "FROM diagnoses ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        recent = [{"time": r["created_at"][:19] if r["created_at"] else "?",
                    "code": r["fault_code"], "equipment": r["equipment_type"] or "?",
                    "source": r["source"] or "?", "confidence": r["confidence"] or 0}
                   for r in rows]
        db.close()
    except Exception:
        pass

    # Stripe balance
    stripe_balance = 0
    if STRIPE_SECRET_KEY:
        try:
            req = _ur.Request("https://api.stripe.com/v1/balance",
                              headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"})
            with _ur.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                stripe_balance = data["available"][0]["amount"]
        except Exception:
            pass

    # AI engine status
    ai_engine = "Cloud"
    ai_provider = "MiniMax M2.7 → Groq → LM Studio"

    # Service health
    services = []
    for name, url in [("IndAutomation", "https://indautomation.onrender.com/api/health"),
                       ("ClawGrab", "https://clawgrab.onrender.com/health"),
                       ("Crucix", "https://crucix.live"),
                       ("Debt Clock", "https://us-debt-clock.onrender.com")]:
        try:
            req = _ur.Request(url, headers={"User-Agent": "Dashboard/1.0"})
            with _ur.urlopen(req, timeout=5) as resp:
                services.append({"name": name, "status": "up", "url": url})
        except Exception:
            services.append({"name": name, "status": "down", "url": url})

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "stats": {"total_diagnoses": total_diagnoses, "fault_codes": len(load_fault_db()),
                  "stripe_balance": stripe_balance, "ai_engine": ai_engine, "ai_provider": ai_provider},
        "services": services,
        "top_faults": top_faults,
        "recent": recent,
    })


# ── Also keep JSON API for programmatic access ──


@app.post("/api/diagnose")
async def api_diagnose(
    equipment_type: str = Form(""),
    fault_code: str = Form(""),
    symptoms: str = Form(""),
    photo: UploadFile | None = File(None),
):
    photo_result = None
    if photo and photo.filename:
        photo_bytes = await photo.read()
        if photo_bytes:
            photo_result = analyze_photo(photo_bytes, equipment_type, fault_code, CONFIG)

    result = diagnose_fault(equipment_type, fault_code, symptoms, photo_result, CONFIG)
    diagnosis_id = _save_diagnosis(result, equipment_type, fault_code, symptoms, photo_result)
    result["diagnosis_id"] = diagnosis_id
    return JSONResponse(result)


@app.get("/api/history")
async def api_history(limit: int = 50):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM diagnoses ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return JSONResponse([dict(r) for r in rows])


@app.post("/api/feedback")
async def submit_feedback(request: Request):
    """Record user feedback on a diagnosis result."""
    body = await request.json()
    diagnosis_id = body.get("diagnosis_id")
    helpful = body.get("helpful")
    comment = body.get("comment", "").strip()[:500]

    if diagnosis_id is None or helpful is None:
        return JSONResponse({"error": "diagnosis_id and helpful are required"}, status_code=400)

    now = datetime.now(timezone.utc).isoformat()
    try:
        db = get_db()
        # Verify diagnosis exists
        row = db.execute("SELECT id FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()
        if not row:
            db.close()
            return JSONResponse({"error": "Diagnosis not found"}, status_code=404)
        db.execute(
            "INSERT INTO diagnosis_feedback (diagnosis_id, helpful, comment, created_at) VALUES (?,?,?,?)",
            (diagnosis_id, 1 if helpful else 0, comment or None, now),
        )
        db.commit()
        db.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # Log for SAFLA learning
    try:
        entry = json.dumps({
            "timestamp": now, "diagnosis_id": diagnosis_id,
            "helpful": bool(helpful), "comment": comment,
        })
        with open(LOGS_PATH / "feedback.jsonl", "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

    return JSONResponse({"status": "ok"})


@app.get("/api/affiliate/click")
async def affiliate_click(request: Request, url: str = "", supplier: str = "", part: str = ""):
    """Log Amazon affiliate click then redirect to supplier URL."""
    if not url:
        return JSONResponse({"error": "url required"}, status_code=400)
    try:
        entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "supplier": supplier,
            "part": part,
            "url": url,
            "referrer": request.headers.get("referer", ""),
        })
        with open(LOGS_PATH / "affiliate_clicks.jsonl", "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass
    from starlette.responses import RedirectResponse
    return RedirectResponse(url=url, status_code=302)


@app.get("/api/affiliate/stats")
async def affiliate_stats():
    """Return aggregate affiliate click counts by supplier."""
    log_path = LOGS_PATH / "affiliate_clicks.jsonl"
    if not log_path.exists():
        return JSONResponse({"total": 0, "by_supplier": {}})
    counts: dict[str, int] = {}
    total = 0
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                s = d.get("supplier", "unknown")
                counts[s] = counts.get(s, 0) + 1
                total += 1
    except Exception:
        pass
    return JSONResponse({"total": total, "by_supplier": counts})


@app.get("/api/feedback/stats")
async def feedback_stats():
    """Return aggregate feedback statistics."""
    db = get_db()
    row = db.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN helpful=1 THEN 1 ELSE 0 END) as helpful_count
        FROM diagnosis_feedback
    """).fetchone()
    db.close()
    total = (row["total"] or 0) if row else 0
    helpful_count = (row["helpful_count"] or 0) if row else 0
    return JSONResponse({
        "total": total,
        "helpful": helpful_count,
        "not_helpful": total - helpful_count,
        "satisfaction_pct": round(helpful_count / total * 100, 1) if total > 0 else 0,
    })


# ── Chat — conversational diagnostic assistant ──────────────────────────────

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

CHAT_SYSTEM_PROMPT = """You are RepairXpertAI, an expert industrial maintenance diagnostic assistant. You help field technicians diagnose equipment faults, find parts, and get step-by-step repair instructions.

You have access to a database of 313 fault codes across 11 equipment types: Allen-Bradley PLCs, VFDs, servos, conveyors, palletizers, pilers, AS/RS, motors, packaging, and general industrial equipment.

When a technician describes a problem:
1. Identify the likely fault code(s) from the database
2. Explain the probable causes in plain language
3. Give step-by-step fix instructions a field tech can follow
4. Suggest specific replacement parts with supplier names
5. Share field tricks — the stuff that saves time on the floor

Be direct. Talk like a fellow tech, not a manual. If you're unsure, say so and suggest what to check first.

Keep answers concise — the tech is reading this on their phone, possibly standing on a ladder."""


def _call_deepseek(messages: list, max_tokens: int = 800) -> str | None:
    """Call DeepSeek chat API. Returns response text or None on failure."""
    key = DEEPSEEK_API_KEY
    if not key:
        # Fallback: try LM Studio local
        return _call_lm_studio_chat(messages, max_tokens)
    try:
        import urllib.request
        data = json.dumps({
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[CHAT] DeepSeek error: {e}")
        return _call_lm_studio_chat(messages, max_tokens)


def _call_lm_studio_chat(messages: list, max_tokens: int = 800) -> str | None:
    """Fallback: call LM Studio local for chat."""
    try:
        import urllib.request
        base_url = CONFIG.get("lm_studio", {}).get("base_url", "http://127.0.0.1:1234/v1")
        model = CONFIG.get("lm_studio", {}).get("text_model", "qwen3.5-9b")
        data = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception:
        return None


def _find_relevant_faults(query: str, top_n: int = 5) -> list[dict]:
    """Search fault DB for entries relevant to the user's query."""
    from indauto.diagnosis.engine import _fuzzy_score, _symptom_score
    db = load_fault_db()
    scored = []
    for entry in db:
        code_s = _fuzzy_score(query, entry)
        symp_s = _symptom_score(query, entry)
        combined = max(code_s, symp_s)
        if combined > 0.2:
            scored.append((combined, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_n]]


def _build_context_from_faults(faults: list[dict]) -> str:
    """Build concise context string from matched fault entries."""
    if not faults:
        return ""
    parts = ["Relevant fault codes from database:"]
    for f in faults:
        parts.append(f"\n[{f.get('code','?')}] {f.get('name','?')} ({f.get('equipment_type','?')})")
        parts.append(f"  Description: {f.get('description','')[:200]}")
        causes = f.get("probable_causes", [])
        if causes:
            parts.append(f"  Probable causes: {'; '.join(causes[:3])}")
        steps = f.get("fix_steps", [])
        if steps:
            parts.append(f"  Fix steps: {'; '.join(steps[:3])}")
        trick = f.get("field_trick", "")
        if trick:
            parts.append(f"  Field trick: {trick[:150]}")
        pcat = f.get("parts_category", "")
        if pcat:
            suggested = get_parts_for_category(pcat)
            if suggested:
                pnames = [p.get("name", "") for p in suggested[:3]]
                parts.append(f"  Parts: {', '.join(pnames)}")
    return "\n".join(parts)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """Conversational diagnostic assistant. Accepts message + history."""
    body = await request.json()
    user_message = body.get("message", "").strip()
    history = body.get("history", [])  # list of {role, content}

    if not user_message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Search fault DB for relevant context
    relevant_faults = _find_relevant_faults(user_message)
    context = _build_context_from_faults(relevant_faults)

    # Build messages for LLM
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    # Add context as system message if we found relevant faults
    if context:
        messages.append({"role": "system", "content": context})

    # Add conversation history (last 10 exchanges to stay in token budget)
    for msg in history[-20:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    # Add current message
    messages.append({"role": "user", "content": user_message})

    # Call LLM
    response_text = _call_deepseek(messages)

    if not response_text:
        # Ultimate fallback: use diagnosis engine directly
        try:
            result = diagnose_fault("", user_message, user_message, None, CONFIG)
        except Exception:
            result = {"source": "fallback"}
        if result.get("source") != "fallback":
            response_text = f"**{result.get('fault_name', 'Unknown')}** (Code: {result.get('fault_code', '?')}, Confidence: {result.get('confidence', 0):.0%})\n\n"
            response_text += "**Probable causes:**\n"
            for c in result.get("diagnosis", [])[:3]:
                response_text += f"- {c}\n"
            response_text += "\n**Fix steps:**\n"
            for i, s in enumerate(result.get("fix_steps", [])[:5], 1):
                response_text += f"{i}. {s}\n"
            if result.get("field_trick"):
                response_text += f"\n**Field trick:** {result['field_trick']}"
            response_text += "\n\n*Our AI assistant is temporarily busy. This answer is from our fault code database. For full AI-powered diagnosis, try again in a moment.*"
        elif relevant_faults:
            # AI down + diagnosis engine couldn't match, but we found faults in DB search
            response_text = "Our AI assistant is temporarily busy. Here's what we found in our fault code database:\n\n"
            for f in relevant_faults[:3]:
                response_text += f"- **{f.get('code', '?')}** — {f.get('name', 'Unknown')}\n"
                symptoms = f.get("symptoms", [])
                if symptoms:
                    response_text += f"  Symptoms: {', '.join(symptoms[:3])}\n"
            response_text += "\nFor full AI-powered diagnosis, try again in a moment."
        else:
            response_text = "Our AI assistant is temporarily busy and we couldn't find an exact match in the fault code database. Please try again in a moment, or include a specific fault code (e.g. F001, E-Stop) for a direct database lookup."

    # Log chat for learning
    try:
        log_path = LOGS_PATH / "chat_log.jsonl"
        entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_message": user_message[:500],
            "faults_matched": len(relevant_faults),
            "fault_codes": [f.get("code") for f in relevant_faults],
            "response_length": len(response_text),
            "source": "deepseek" if DEEPSEEK_API_KEY else "lm_studio",
        })
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

    return JSONResponse({
        "response": response_text,
        "faults_referenced": [{"code": f.get("code"), "name": f.get("name")} for f in relevant_faults],
    })


# ── Helpers ──


def _save_diagnosis(result: dict, equipment_type: str, fault_code: str,
                    symptoms: str, photo_result: dict | None) -> int:
    """Persist diagnosis to SQLite and log outcome for SAFLA learning. Returns row ID."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    cursor = db.execute(
        """INSERT INTO diagnoses
           (created_at, equipment_type, fault_code, symptoms, fault_name,
            diagnosis, fix_steps, photo_analysis, severity, confidence, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            now,
            equipment_type,
            fault_code,
            symptoms,
            result.get("fault_name", ""),
            json.dumps(result.get("diagnosis", [])),
            json.dumps(result.get("fix_steps", [])),
            json.dumps(photo_result) if photo_result else None,
            result.get("severity", "medium"),
            result.get("confidence", 0),
            result.get("source", "unknown"),
        ),
    )
    diagnosis_id = cursor.lastrowid
    db.commit()
    db.close()

    # Log diagnosis outcome for SAFLA self-learning feedback loop
    _log_diagnosis_outcome(now, equipment_type, fault_code, symptoms, result)
    return diagnosis_id


def _log_diagnosis_outcome(timestamp: str, equipment_type: str, fault_code: str,
                           symptoms: str, result: dict):
    """Log diagnosis outcome to JSONL for SAFLA learning cycle consumption."""
    try:
        log_path = LOGS_PATH / "diagnosis_outcomes.jsonl"
        entry = json.dumps({
            "timestamp": timestamp,
            "equipment_type": equipment_type,
            "fault_code": fault_code,
            "symptoms": symptoms[:200] if symptoms else "",
            "matched_fault": result.get("fault_code", ""),
            "fault_name": result.get("fault_name", ""),
            "confidence": result.get("confidence", 0),
            "source": result.get("source", "unknown"),
            "severity": result.get("severity", "medium"),
            "had_photo": bool(result.get("photo_insight")),
            "parts_suggested": len(result.get("suggested_parts", [])),
        })
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # Never block diagnosis on logging failure


# ── Matchmaker /connect ───────────────────────────────────────────────────────
CONNECT_DB_PATH = ROOT / "data" / "matchmaker_leads.jsonl"


@app.get("/funnel", response_class=HTMLResponse)
async def funnel_dashboard(request: Request):
    """Conversion funnel dashboard — chat → diagnosis → checkout → payment."""
    import json as _json
    from datetime import datetime as _dt

    logs = ROOT / "logs"
    db_path = ROOT / "data" / "diagnosis_log.db"

    def _count_jsonl(path, filter_fn=None):
        if not path.exists():
            return 0
        c = 0
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = _json.loads(ln)
                if filter_fn is None or filter_fn(r):
                    c += 1
            except Exception:
                pass
        return c

    chat_sessions = _count_jsonl(logs / "chat_log.jsonl")
    diagnoses_total = _count_jsonl(logs / "diagnosis_outcomes.jsonl")
    diagnoses_high = _count_jsonl(logs / "diagnosis_outcomes.jsonl",
                                  lambda r: r.get("confidence", 0) >= 0.8)
    checkout_leads = 0
    if db_path.exists():
        try:
            _db = sqlite3.connect(str(db_path))
            row = _db.execute("SELECT COUNT(*) FROM checkout_leads").fetchone()
            checkout_leads = row[0] if row else 0
            _db.close()
        except Exception:
            pass
    stripe_payments = _count_jsonl(logs / "stripe_events.jsonl",
                                   lambda r: r.get("event") == "checkout.session.completed")

    funnel = [
        {"stage": "Chat Sessions",    "count": chat_sessions,    "icon": "\U0001f4ac"},
        {"stage": "Diagnoses Run",    "count": diagnoses_total,  "icon": "\U0001f50d"},
        {"stage": "High Confidence",  "count": diagnoses_high,   "icon": "\u2705"},
        {"stage": "Checkout Leads",   "count": checkout_leads,   "icon": "\U0001f6d2"},
        {"stage": "Payments",         "count": stripe_payments,  "icon": "\U0001f4b3"},
    ]

    conversion_rates: dict = {}
    for i in range(1, len(funnel)):
        prev = funnel[i - 1]["count"]
        curr = funnel[i]["count"]
        rate = round(curr / prev * 100, 1) if prev > 0 else 0.0
        key = f"{funnel[i-1]['stage']} \u2192 {funnel[i]['stage']}"
        conversion_rates[key] = rate

    # Top equipment breakdown
    eq_counts: dict = {}
    diag_path = logs / "diagnosis_outcomes.jsonl"
    if diag_path.exists():
        for ln in diag_path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = _json.loads(ln)
                eq = r.get("equipment_type", "unknown") or "unknown"
                eq_counts[eq] = eq_counts.get(eq, 0) + 1
            except Exception:
                pass
    top_equipment = [{"type": k, "count": v}
                     for k, v in sorted(eq_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

    return templates.TemplateResponse("funnel_dashboard.html", {
        "request": request,
        "funnel": funnel,
        "conversion_rates": conversion_rates,
        "top_equipment": top_equipment,
        "generated_at": _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })


@app.get("/api/funnel")
async def api_funnel():
    """Return funnel + usage stats as JSON for Finance agent consumption."""
    def _count_jsonl(path, predicate=None):
        if not path.exists():
            return 0
        c = 0
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = _json.loads(ln)
                if predicate is None or predicate(r):
                    c += 1
            except Exception:
                pass
        return c

    logs = Path(os.environ.get("LOGS_PATH", "/app/data/logs"))
    db_path = DB_PATH

    chat_sessions = _count_jsonl(logs / "chat_log.jsonl")
    diagnoses_total = _count_jsonl(logs / "diagnosis_outcomes.jsonl")
    diagnoses_high = _count_jsonl(logs / "diagnosis_outcomes.jsonl",
                                  lambda r: r.get("confidence", 0) >= 0.8)
    checkout_leads = 0
    stripe_payments = 0
    if db_path.exists():
        try:
            _db = sqlite3.connect(str(db_path))
            row = _db.execute("SELECT COUNT(*) FROM checkout_leads").fetchone()
            checkout_leads = row[0] if row else 0
            _db.close()
        except Exception:
            pass
    stripe_payments = _count_jsonl(logs / "stripe_events.jsonl",
                                   lambda r: r.get("event") == "checkout.session.completed")

    return JSONResponse({
        "generated_at": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chat_sessions": chat_sessions,
        "diagnoses_total": diagnoses_total,
        "diagnoses_high_confidence": diagnoses_high,
        "checkout_leads": checkout_leads,
        "stripe_payments": stripe_payments,
        "conversion_rates": {
            "diagnoses_to_checkout": round(checkout_leads / diagnoses_total * 100, 1) if diagnoses_total > 0 else 0.0,
            "checkout_to_payment": round(stripe_payments / checkout_leads * 100, 1) if checkout_leads > 0 else 0.0,
        },
    })


@app.get("/connect", response_class=HTMLResponse)
async def connect_page(request: Request):
    return templates.TemplateResponse("connect.html", {"request": request})


@app.post("/connect", response_class=HTMLResponse)
async def connect_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    company: str = Form(""),
    message: str = Form(""),
):
    email = email.strip().lower()
    name = name.strip()
    role = role.strip()

    if not email or "@" not in email:
        return templates.TemplateResponse(
            "connect.html", {"request": request, "error": "Valid email required."}
        )
    if role not in ("tech", "plant_manager", "vendor", "builder"):
        return templates.TemplateResponse(
            "connect.html", {"request": request, "error": "Please select a valid role."}
        )

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "ts": now,
        "name": name,
        "email": email,
        "role": role,
        "company": company.strip(),
        "message": message.strip()[:500],
    }

    # Persist lead
    try:
        with open(CONNECT_DB_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Notify via Resend
    if RESEND_API_KEY:
        try:
            import httpx
            role_labels = {
                "tech": "Field Tech / Maintenance",
                "plant_manager": "Plant Manager",
                "vendor": "Vendor / Supplier",
                "builder": "Product Builder",
            }
            subject = f"[Matchmaker] New {role_labels.get(role, role)} — {name}"
            body_html = (
                f"<h2>New /connect submission</h2>"
                f"<p><b>Name:</b> {name}<br>"
                f"<b>Email:</b> {email}<br>"
                f"<b>Role:</b> {role_labels.get(role, role)}<br>"
                f"<b>Company:</b> {company or '—'}<br>"
                f"<b>Message:</b> {message or '—'}</p>"
            )
            httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    # 2026-04-08 reply-inbox fix: indautomation.onrender.com
                    # cannot receive. Use verified repairxpertai.com sender
                    # with reply_to pointing to Eric's Gmail.
                    "from": "IndAutomation <hello@repairxpertai.com>",
                    "to": ["ericwestmail@gmail.com"],
                    "reply_to": "ericwestmail@gmail.com",
                    "subject": subject,
                    "html": body_html,
                },
                timeout=8,
            )
        except Exception:
            pass

    return templates.TemplateResponse("connect_success.html", {"request": request, "role": role, "name": name})


# ── Dispatch board (connect field techs to open repair jobs) ─────────────────
DISPATCH_DB_PATH = ROOT / "data" / "dispatches.jsonl"
DISPATCH_URGENCIES = ("low", "normal", "urgent", "critical")


def _load_dispatches(limit: int = 50, status: str = "open"):
    """Return dispatch entries, newest first."""
    if not DISPATCH_DB_PATH.exists():
        return []
    rows = []
    try:
        for ln in DISPATCH_DB_PATH.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except Exception:
                continue
            if status and row.get("status") != status:
                continue
            rows.append(row)
    except Exception:
        return []
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return rows[:limit]


@app.get("/dispatch", response_class=HTMLResponse)
async def dispatch_page(request: Request):
    """Dispatch board — post an open repair job or claim one."""
    dispatches = _load_dispatches(limit=50, status="open")
    return templates.TemplateResponse(
        "dispatch.html",
        {
            "request": request,
            "dispatches": dispatches,
            "urgencies": DISPATCH_URGENCIES,
        },
    )


@app.post("/dispatch", response_class=HTMLResponse)
async def dispatch_submit(
    request: Request,
    company: str = Form(...),
    contact_email: str = Form(...),
    equipment: str = Form(""),
    fault_code: str = Form(""),
    location: str = Form(""),
    urgency: str = Form("normal"),
    description: str = Form(""),
):
    contact_email = contact_email.strip().lower()
    company = company.strip()
    urgency = urgency.strip().lower()

    if not company:
        dispatches = _load_dispatches(limit=50, status="open")
        return templates.TemplateResponse(
            "dispatch.html",
            {
                "request": request,
                "dispatches": dispatches,
                "urgencies": DISPATCH_URGENCIES,
                "error": "Company / plant name required.",
            },
        )
    if not contact_email or "@" not in contact_email:
        dispatches = _load_dispatches(limit=50, status="open")
        return templates.TemplateResponse(
            "dispatch.html",
            {
                "request": request,
                "dispatches": dispatches,
                "urgencies": DISPATCH_URGENCIES,
                "error": "Valid contact email required.",
            },
        )
    if urgency not in DISPATCH_URGENCIES:
        urgency = "normal"

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "ts": now,
        "status": "open",
        "company": company[:120],
        "contact_email": contact_email[:160],
        "equipment": equipment.strip()[:120],
        "fault_code": fault_code.strip()[:40],
        "location": location.strip()[:160],
        "urgency": urgency,
        "description": description.strip()[:800],
    }

    try:
        DISPATCH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DISPATCH_DB_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Notify operator so the job can be routed to a matched tech from /connect
    if RESEND_API_KEY:
        try:
            import httpx
            urgency_label = {
                "low": "Low", "normal": "Normal",
                "urgent": "Urgent", "critical": "CRITICAL",
            }.get(urgency, urgency)
            subject = f"[Dispatch] {urgency_label} — {company}"
            body_html = (
                f"<h2>New dispatch request</h2>"
                f"<p><b>Company:</b> {company}<br>"
                f"<b>Contact:</b> {contact_email}<br>"
                f"<b>Equipment:</b> {entry['equipment'] or '—'}<br>"
                f"<b>Fault code:</b> {entry['fault_code'] or '—'}<br>"
                f"<b>Location:</b> {entry['location'] or '—'}<br>"
                f"<b>Urgency:</b> {urgency_label}<br>"
                f"<b>Description:</b> {entry['description'] or '—'}</p>"
                f"<p>Route this job to a matched tech from /connect.</p>"
            )
            httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "IndAutomation <hello@repairxpertai.com>",
                    "to": ["ericwestmail@gmail.com"],
                    "reply_to": contact_email,
                    "subject": subject,
                    "html": body_html,
                },
                timeout=8,
            )
        except Exception:
            pass

    dispatches = _load_dispatches(limit=50, status="open")
    return templates.TemplateResponse(
        "dispatch.html",
        {
            "request": request,
            "dispatches": dispatches,
            "urgencies": DISPATCH_URGENCIES,
            "success": f"Dispatch posted for {company}. A matched tech will be contacted at {contact_email}.",
        },
    )


@app.get("/api/dispatch")
async def api_dispatch_list(status: str = "open", limit: int = 50):
    """JSON feed of dispatches — for field-tech mobile clients."""
    try:
        limit = max(1, min(int(limit), 200))
    except Exception:
        limit = 50
    rows = _load_dispatches(limit=limit, status=status or "open")
    return JSONResponse({"count": len(rows), "dispatches": rows})


@app.post("/api/lead")
async def capture_lead(request: Request):
    """Lead capture: create Stripe customer + send welcome email.

    Body (JSON): {"email": "...", "name": "...", "plan": "pro"|"enterprise"|"free"}
    Returns: {"ok": true, "stripe_customer_id": "...", "email_sent": true}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON"})

    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()
    plan = (body.get("plan") or "free").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Valid email required"})

    now = datetime.now(timezone.utc).isoformat()
    stripe_customer_id = None
    email_sent = False

    # 1. Create Stripe customer
    if _stripe_available:
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name or None,
                metadata={"plan": plan, "source": "api_lead"},
            )
            stripe_customer_id = customer.id
        except Exception as e:
            _log_stripe_event("lead_stripe_error", {"email": email, "error": str(e)})

    # 2. Log lead to SQLite
    try:
        db = get_db()
        db.execute(
            "INSERT INTO checkout_leads (created_at, email, plan, stripe_session_id, status) VALUES (?,?,?,?,?)",
            (now, email, plan, stripe_customer_id or "", "lead_captured"),
        )
        db.commit()
        db.close()
    except Exception as e:
        _log_stripe_event("lead_db_error", {"email": email, "error": str(e)})

    # 3. Send welcome email via Resend
    if RESEND_API_KEY:
        plan_label = {"pro": "Pro ($19/mo)", "enterprise": "Enterprise ($99/mo)"}.get(plan, "Free")
        greeting = f"Hi {name}," if name else "Hi there,"
        html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">Welcome to RepairXpert Industrial Automation</h2>
<p>{greeting}</p>
<p>You're now on our radar for the <strong>{plan_label}</strong> plan. We help field technicians diagnose faults faster with AI — 313+ fault codes, parts recommendations, and direct chat with our diagnostic engine.</p>
<p style="margin:1.5rem 0"><a href="https://indautomation.onrender.com/pricing" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">View Plans &amp; Pricing</a></p>
<p style="color:#8b949e;font-size:0.85rem">Questions? Reply to this email or visit indautomation.onrender.com. Cancel anytime — no contracts.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians</p>
</div>"""
        try:
            import urllib.request as _urlreq
            payload = json.dumps({
                "from": "RepairXpert <hello@repairxpertai.com>",
                "to": [email],
                "reply_to": "ericwestmail@gmail.com",
                "subject": "Welcome to RepairXpert Industrial Automation",
                "html": html_body,
            }).encode()
            req = _urlreq.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {RESEND_API_KEY}"},
            )
            with _urlreq.urlopen(req, timeout=10):
                email_sent = True
        except Exception as e:
            _log_stripe_event("lead_email_failed", {"email": email, "error": str(e)})

    _log_stripe_event("lead_captured", {"email": email, "plan": plan})
    return JSONResponse(content={"ok": True, "stripe_customer_id": stripe_customer_id, "email_sent": email_sent})


# ── Command Center ─────────────────────────────────────────────────────────────


@app.get("/command-center", response_class=HTMLResponse)
async def command_center(request: Request):
    """Command Center — single-page ops dashboard for all ventures."""
    return templates.TemplateResponse("command_center.html", {"request": request})


@app.get("/api/command-center-data")
async def command_center_data(request: Request):
    """Aggregated data for the Command Center dashboard."""
    import subprocess
    import urllib.request as _ccur

    now = datetime.now(timezone.utc)
    result = {
        "generated_at": now.isoformat(),
        "services": {},
        "mrr": {},
        "last_actions": {},
        "venture_details": {},
        "revenue_loop_status": "unknown",
        "revenue_loop_log": [],
        "ai_engines_active": 0,
        "brain_cycles_24h": 0,
        "outreach": {"emails_sent": "93+", "tweets": "43+", "articles": "14", "replies": "0"},
        "recent_emails": [],
        "git_log": [],
        "crypto": {},
        "github_actions": [],
        "alerts": [],
    }

    # --- Service health checks ---
    health_urls = {
        "indautomation": "https://indautomation.onrender.com/api/health",
        "clawgrab": "https://clawgrab.onrender.com/health",
        "vendorad": "https://vendor-ad-network.onrender.com/health",
        "debtclock": "https://us-debt-clock.onrender.com",
    }
    for svc, url in health_urls.items():
        try:
            req = _ccur.Request(url, headers={"User-Agent": "CommandCenter/1.0"})
            with _ccur.urlopen(req, timeout=6) as resp:
                result["services"][svc] = "up" if resp.status < 400 else "down"
        except Exception:
            result["services"][svc] = "down"

    # Local-only services
    for local_svc in ["lite", "cryptovault", "soltrade", "cryptotrading",
                       "content", "dealsniper", "clawgrab_mcp", "invoiceflow", "procurement"]:
        result["services"][local_svc] = "local"

    # Crucix
    try:
        req = _ccur.Request("https://crucix.live", headers={"User-Agent": "CommandCenter/1.0"})
        with _ccur.urlopen(req, timeout=6) as resp:
            result["services"]["crucix"] = "up" if resp.status < 400 else "down"
    except Exception:
        result["services"]["crucix"] = "down"

    # --- IndAutomation details from local DB ---
    try:
        db = get_db()
        row = db.execute("SELECT COUNT(*) as cnt, MAX(created_at) as last_ts FROM diagnoses").fetchone()
        leads_row = db.execute("SELECT COUNT(*) as cnt FROM checkout_leads").fetchone()
        converted_row = db.execute("SELECT COUNT(*) as cnt FROM checkout_leads WHERE status='converted'").fetchone()
        result["venture_details"]["indautomation"] = {
            "total_diagnoses": row["cnt"] if row else 0,
            "last_diagnosis": row["last_ts"] if row else None,
            "fault_codes": len(load_fault_db()),
            "leads": leads_row["cnt"] if leads_row else 0,
            "customers": converted_row["cnt"] if converted_row else 0,
            "notes": "Stripe LIVE. Cloud AI 24/7 via MiniMax M2.7 + Groq fallback.",
        }
        db.close()
    except Exception:
        pass

    # --- Revenue loop status ---
    try:
        result["revenue_loop_status"] = "running" if _revenue_thread and _revenue_thread.is_alive() else "stopped"
        result["revenue_loop_log"] = get_revenue_log()
    except Exception:
        result["revenue_loop_log"] = []

    # --- AI engine count ---
    engines = 0
    if result["revenue_loop_status"] == "running":
        engines += 1  # MiniMax revenue loop
    # Cloud worker always runs inside this process
    engines += 1  # Cloud worker
    result["ai_engines_active"] = engines
    result["brain_cycles_24h"] = len([l for l in result["revenue_loop_log"] if "analyze" in l.lower() or "brain" in l.lower()])

    # --- MRR (all $0 currently) ---
    for v in ["indautomation", "clawgrab", "lite", "crucix", "cryptovault",
              "soltrade", "cryptotrading", "content", "vendorad", "debtclock",
              "dealsniper", "clawgrab_mcp", "invoiceflow", "procurement"]:
        result["mrr"][v] = "$0"

    # --- Stripe balance ---
    stripe_bal = "--"
    if _stripe_available:
        try:
            bal = stripe.Balance.retrieve()
            for b in bal.get("available", []):
                if b.get("currency") == "usd":
                    stripe_bal = f"${b['amount'] / 100:.2f}"
                    break
        except Exception:
            stripe_bal = "error"
    result["crypto"]["stripe_balance"] = stripe_bal

    # --- Crypto data (static from known state) ---
    result["crypto"]["soltrade_status"] = "LIVE"
    result["crypto"]["signal"] = "--"
    result["crypto"]["rsi"] = "--"
    result["crypto"]["last_trade"] = "--"
    result["crypto"]["sol_balance"] = "0.017 SOL"

    # Try to read live crypto state if available
    crypto_state_path = Path("C:/Users/Admin-RP/Documents/CryptoTradingAgent/state")
    try:
        if crypto_state_path.exists():
            for f in sorted(crypto_state_path.glob("*.json"), reverse=True)[:1]:
                cdata = json.loads(f.read_text(encoding="utf-8"))
                result["crypto"]["signal"] = cdata.get("signal", "--")
                result["crypto"]["rsi"] = str(cdata.get("rsi", "--"))
                result["crypto"]["last_trade"] = cdata.get("last_trade", "--")
    except Exception:
        pass

    # --- Git log (IndAutomation repo) ---
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", "--format=%h|%s|%an", "-20"],
            capture_output=True, text=True, timeout=5,
            cwd=str(ROOT),
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().split("\n"):
                parts = line.split("|", 2)
                if len(parts) == 3:
                    result["git_log"].append({
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                    })
    except Exception:
        pass

    # --- Last actions ---
    result["last_actions"]["indautomation"] = "Cloud AI 24/7, cart recovery active"
    result["last_actions"]["clawgrab"] = "v2.24.0 deployed, YouTube fix pending"
    result["last_actions"]["lite"] = "Stripe link works, Gumroad 404"
    result["last_actions"]["crucix"] = "Pricing page + Stripe products"
    result["last_actions"]["cryptovault"] = "Monthly scan scheduled"
    result["last_actions"]["soltrade"] = "LIVE mode, aggressive RSI 40"
    result["last_actions"]["cryptotrading"] = "99% backtest accuracy"
    result["last_actions"]["content"] = "43 tweets, 14 articles"
    result["last_actions"]["vendorad"] = "API only, no frontend"
    result["last_actions"]["debtclock"] = "Live WebSocket"
    result["last_actions"]["dealsniper"] = "9 sources configured"
    result["last_actions"]["clawgrab_mcp"] = "CAPTCHA blocked"
    result["last_actions"]["invoiceflow"] = "Rebrand 60%"
    result["last_actions"]["procurement"] = "Gated: 3 customers"

    # --- GitHub Actions ---
    result["github_actions"] = [
        {"name": "Revenue Agent (24/7)", "status": "pass", "last_run": "Continuous on Render"},
        {"name": "Triple Blind QA", "status": "unknown", "last_run": "--"},
        {"name": "OpenClaw Agent", "status": "unknown", "last_run": "--"},
    ]

    # --- Recent emails from Stripe event log ---
    try:
        event_log = LOGS_PATH / "stripe_events.jsonl"
        if event_log.exists():
            lines = event_log.read_text(encoding="utf-8").strip().split("\n")
            for line in reversed(lines[-50:]):
                try:
                    evt = json.loads(line)
                    if "email" in evt.get("type", "").lower() or "recovery" in evt.get("type", ""):
                        d = evt.get("data", {})
                        result["recent_emails"].append({
                            "time": evt.get("ts", "")[:19],
                            "to": d.get("email", ""),
                            "subject": evt.get("type", ""),
                        })
                        if len(result["recent_emails"]) >= 10:
                            break
                except Exception:
                    continue
    except Exception:
        pass

    # --- Alerts ---
    # Zero replies
    result["alerts"].append({"level": "red", "message": "OUTREACH: 93+ emails sent, 0 human replies. Adjust targeting or copy."})

    # Zero MRR
    result["alerts"].append({"level": "red", "message": "REVENUE: $0 external MRR across all ventures."})

    # Service health alerts
    for svc, status in result["services"].items():
        if status == "down":
            result["alerts"].append({"level": "red", "message": f"SERVICE DOWN: {svc}"})

    # Gumroad 404
    result["alerts"].append({"level": "yellow", "message": "LITE: Gumroad product page returns 404. Stripe link works."})

    # YouTube
    result["alerts"].append({"level": "yellow", "message": "CLAWGRAB: YouTube grab times out on Render (IP blocked)."})

    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG["app"]["host"], port=CONFIG["app"]["port"])
