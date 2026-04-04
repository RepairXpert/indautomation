"""RepairXpert Industrial Automation — FastAPI diagnostic tool for field techs."""
import json
import os
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

DB_PATH = ROOT / "data" / "diagnosis_log.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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

    if plan not in STRIPE_PRICE_IDS:
        return JSONResponse({"error": f"Unknown plan: {plan}"}, status_code=400)

    price_id = STRIPE_PRICE_IDS[plan]
    if not price_id:
        return JSONResponse(
            {"error": f"Stripe Price ID not configured for '{plan}'. Set STRIPE_PRICE_ID_{plan.upper()} in env."},
            status_code=503,
        )

    # Build absolute URLs for success/cancel redirects
    base_url = str(request.base_url).rstrip("/")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/checkout/cancel",
        )
        return JSONResponse({"checkout_url": session.url})
    except stripe.error.StripeError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/checkout/success", response_class=HTMLResponse)
async def checkout_success(request: Request):
    return templates.TemplateResponse("checkout_success.html", {"request": request})


@app.get("/checkout/cancel", response_class=HTMLResponse)
async def checkout_cancel(request: Request):
    return templates.TemplateResponse("checkout_cancel.html", {"request": request})


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


@app.get("/sitemap.xml")
async def sitemap(request: Request):
    """Dynamic XML sitemap for SEO — lists all fault code pages."""
    faults = load_fault_db()
    base = str(request.base_url).rstrip("/")
    urls = [
        f'<url><loc>{base}/</loc><priority>1.0</priority></url>',
        f'<url><loc>{base}/faults</loc><priority>0.9</priority></url>',
        f'<url><loc>{base}/pricing</loc><priority>0.8</priority></url>',
    ]
    for f in faults:
        code = f.get("code", "")
        urls.append(f'<url><loc>{base}/fault/{code}</loc><priority>0.7</priority></url>')
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
    """Persist diagnosis to SQLite."""
    db = get_db()
    db.execute(
        """INSERT INTO diagnoses
           (created_at, equipment_type, fault_code, symptoms, fault_name,
            diagnosis, fix_steps, photo_analysis, severity, confidence, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now(timezone.utc).isoformat(),
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG["app"]["host"], port=CONFIG["app"]["port"])
