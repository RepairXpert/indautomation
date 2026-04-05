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

app = FastAPI(title="RepairXpert IndAutomation", version="1.0.0")
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
    db.commit()
    return db


# ── Routes ──────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    equipment = _load_equipment()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "equipment": equipment,
    })


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

    if STRIPE_WEBHOOK_SECRET and _stripe_available:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            return JSONResponse({"error": "Invalid signature"}, status_code=400)
    else:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid payload"}, status_code=400)

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
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://indautomation.onrender.com")
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

    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://indautomation.onrender.com")
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
            "from": "RepairXpert <hello@getclawgrab.com>",
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
    _save_diagnosis(result, equipment_type, fault_code, symptoms, photo_result)

    return templates.TemplateResponse("diagnose.html", {
        "request": request,
        "result": result,
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
    return templates.TemplateResponse("history.html", {
        "request": request,
        "entries": entries,
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
        f'<url><loc>{base}/compare</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/maintainx</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/servicetitan</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'<url><loc>{base}/compare/upkeep</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
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
    _save_diagnosis(result, equipment_type, fault_code, symptoms, photo_result)
    return JSONResponse(result)


@app.get("/api/history")
async def api_history(limit: int = 50):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM diagnoses ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return JSONResponse([dict(r) for r in rows])


# ── Helpers ──


def _save_diagnosis(result: dict, equipment_type: str, fault_code: str,
                    symptoms: str, photo_result: dict | None):
    """Persist diagnosis to SQLite and log outcome for SAFLA learning."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute(
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
    db.commit()
    db.close()

    # Log diagnosis outcome for SAFLA self-learning feedback loop
    _log_diagnosis_outcome(now, equipment_type, fault_code, symptoms, result)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG["app"]["host"], port=CONFIG["app"]["port"])
