"""RepairXpert Industrial Automation — FastAPI diagnostic tool for field techs."""
import json
import os
import sys
import sqlite3
from datetime import datetime, timezone
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
    _send_recovery_email(email, plan, base_url)

    return JSONResponse({"status": "ok", "message": "We'll send you a link to complete your subscription."})


def _handle_checkout_completed(session: dict):
    """Mark lead as converted."""
    email = session.get("customer_email", "") or session.get("customer_details", {}).get("email", "")
    if email:
        try:
            db = get_db()
            db.execute("UPDATE checkout_leads SET status='converted' WHERE email=? AND status='pending'", (email,))
            db.commit()
            db.close()
        except Exception:
            pass


def _handle_checkout_expired(session: dict):
    """Send recovery email for expired checkout sessions."""
    email = session.get("customer_email", "")
    if not email:
        return

    # Check if we already sent a recovery for this email recently
    try:
        db = get_db()
        row = db.execute(
            "SELECT recovery_sent_at FROM checkout_leads WHERE email=? ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()
        if row and row["recovery_sent_at"]:
            db.close()
            return  # Already sent recovery
        db.execute(
            "UPDATE checkout_leads SET status='expired', recovery_sent_at=? WHERE email=? AND status='pending'",
            (datetime.now(timezone.utc).isoformat(), email),
        )
        db.commit()
        db.close()
    except Exception:
        pass

    # Determine plan from session metadata
    plan = "pro"
    line_items = session.get("line_items", {}).get("data", [])
    if line_items:
        price_id = line_items[0].get("price", {}).get("id", "")
        if price_id == STRIPE_PRICE_IDS.get("enterprise"):
            plan = "enterprise"

    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://repairxpertai.com")
    _send_recovery_email(email, plan, base_url)


def _send_recovery_email(email: str, plan: str, base_url: str):
    """Send abandoned cart recovery email via Resend."""
    if not RESEND_API_KEY:
        _log_stripe_event("recovery_email_skipped", {"email": email, "reason": "no_resend_key"})
        return

    plan_name = "Enterprise" if plan == "enterprise" else "Pro"
    plan_price = "$49.99" if plan == "enterprise" else "$19.99"

    html_body = f"""<div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;color:#e6edf3;background:#161b22;padding:2rem;border-radius:8px">
<h2 style="color:#f78166;margin-bottom:1rem">You were close to upgrading</h2>
<p>You started checking out the <strong>{plan_name}</strong> plan ({plan_price}/mo) for RepairXpert Industrial Fault Diagnosis but didn't finish.</p>
<p style="margin:1.5rem 0">Ready to pick up where you left off? Your diagnostic power-up is one click away:</p>
<a href="{base_url}/pricing" style="display:inline-block;background:#f78166;color:#fff;padding:0.75rem 2rem;border-radius:6px;text-decoration:none;font-weight:600">Complete Your Subscription</a>
<p style="margin-top:1.5rem;color:#8b949e;font-size:0.85rem">Cancel anytime. No contracts. 313+ fault codes, AI diagnosis, parts recommendations.</p>
<hr style="border:1px solid #30363d;margin:1.5rem 0">
<p style="color:#8b949e;font-size:0.78rem">RepairXpert Industrial Automation — AI-powered fault diagnosis for field technicians</p>
</div>"""

    try:
        import urllib.request
        payload = json.dumps({
            "from": "RepairXpert <hello@repairxpertai.com>",
            "to": [email],
            "subject": f"Complete your RepairXpert {plan_name} subscription",
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
            _log_stripe_event("recovery_email_sent", {"email": email, "plan": plan})
    except Exception as e:
        _log_stripe_event("recovery_email_failed", {"email": email, "error": str(e)})


def _log_stripe_event(event_type: str, data: dict):
    """Append Stripe/recovery event to JSONL log."""
    try:
        log_entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "data": {k: v for k, v in data.items() if k in (
                "id", "customer_email", "email", "plan", "status",
                "amount_total", "currency", "reason", "error",
            )},
        })
        with open(LOGS_PATH / "stripe_events.jsonl", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception:
        pass


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
                    "from": "IndAutomation <hello@indautomation.onrender.com>",
                    "to": ["ericwestmail@gmail.com"],
                    "subject": subject,
                    "html": body_html,
                },
                timeout=8,
            )
        except Exception:
            pass

    return templates.TemplateResponse("connect_success.html", {"request": request, "role": role, "name": name})


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
        plan_label = {"pro": "Pro ($19.99/mo)", "enterprise": "Enterprise ($49.99/mo)"}.get(plan, "Free")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG["app"]["host"], port=CONFIG["app"]["port"])
