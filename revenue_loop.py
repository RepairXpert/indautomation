"""24/7 Autonomous Revenue Loop — runs on Render alongside IndAutomation.

Every 4 hours:
1. Check Stripe for new customers/payments
2. Send follow-up emails to leads via Resend
3. Check all service health
4. Use MiniMax M2.7 to analyze and find opportunities
5. Log everything

No local PC needed. No OpenClaw needed. Pure cloud.
"""
import json
import os
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

SERVICES = {
    "indautomation": "https://indautomation.onrender.com/api/health",
    "clawgrab": "https://clawgrab.onrender.com/health",
    "debtclock": "https://us-debt-clock.onrender.com",
    "vendorad": "https://vendor-ad-network.onrender.com/health",
}

LOG = []


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    LOG.append(entry)
    if len(LOG) > 200:
        LOG.pop(0)
    print(entry)


def _http(url, method="GET", data=None, headers=None, timeout=15):
    """Simple HTTP helper."""
    hdrs = headers or {}
    hdrs.setdefault("User-Agent", "RevenueLoop/1.0")
    if data and isinstance(data, dict):
        data = json.dumps(data).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_services():
    """Ping all services, keep them warm."""
    results = {}
    for name, url in SERVICES.items():
        try:
            urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "RevenueLoop/1.0"}), timeout=10)
            results[name] = "up"
        except Exception:
            results[name] = "down"
    log(f"Health: {results}")
    return results


def check_stripe():
    """Check Stripe for balance and recent payments."""
    if not STRIPE_KEY:
        return {"balance": 0, "recent": 0}
    try:
        data = _http("https://api.stripe.com/v1/balance",
                      headers={"Authorization": f"Bearer {STRIPE_KEY}"})
        balance = data["available"][0]["amount"]

        # Check recent payment intents
        pi_data = _http("https://api.stripe.com/v1/payment_intents?limit=5",
                         headers={"Authorization": f"Bearer {STRIPE_KEY}"})
        succeeded = [p for p in pi_data.get("data", []) if p["status"] == "succeeded"]

        log(f"Stripe: ${balance/100:.2f} balance, {len(succeeded)} recent payments")
        return {"balance": balance, "recent": len(succeeded)}
    except Exception as e:
        log(f"Stripe error: {e}")
        return {"balance": 0, "recent": 0}


def process_cart_recovery():
    """Process abandoned cart recovery queue."""
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return
    try:
        _http("https://indautomation.onrender.com/api/recovery/process",
              method="POST", data={},
              headers={"X-Recovery-Key": webhook_secret})
        log("Cart recovery: processed")
    except Exception as e:
        log(f"Cart recovery: {e}")


def ask_minimax(prompt):
    """Ask MiniMax M2.7 for analysis."""
    if not MINIMAX_KEY:
        return None
    try:
        data = _http(
            "https://api.minimaxi.chat/v1/chat/completions",
            method="POST",
            data={"model": "MiniMax-M2.7", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 500, "temperature": 0.5},
            headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
            timeout=30,
        )
        content = data["choices"][0]["message"]["content"]
        if "<think>" in content:
            content = content.split("</think>")[-1].strip()
        return content
    except Exception as e:
        log(f"MiniMax error: {e}")
        return None


def revenue_cycle():
    """One full revenue cycle."""
    log("=== REVENUE CYCLE START ===")

    # 1. Health check all services (keeps them warm)
    health = check_services()

    # 2. Check Stripe
    stripe = check_stripe()

    # 3. Process cart recovery
    process_cart_recovery()

    # 4. Ask MiniMax for next action
    if stripe["balance"] == 0 or True:  # always analyze
        analysis = ask_minimax(
            f"You are a revenue strategist for RepairXpertAI. "
            f"Current Stripe balance: ${stripe['balance']/100:.2f}. "
            f"Services: {health}. "
            f"Products: IndAutomation ($19/mo fault diagnosis), ClawGrab ($12/mo transcription), "
            f"LITE ($79 offline tool), Crucix ($29/$99 OSINT). "
            f"We have $0 external MRR. 78+ cold emails sent, 0 replies. "
            f"What is the ONE thing we should do RIGHT NOW to get the first paying customer? "
            f"Be specific — name a channel, a message, a target. 100 words max."
        )
        if analysis:
            log(f"MiniMax says: {analysis[:200]}")

    log("=== REVENUE CYCLE END ===")


def loop_forever():
    """Run revenue cycle every 4 hours."""
    time.sleep(120)  # wait for app startup
    while True:
        try:
            revenue_cycle()
        except Exception as e:
            log(f"Cycle error: {e}")
        time.sleep(4 * 3600)  # 4 hours


def start_revenue_loop():
    """Start the revenue loop in a background thread."""
    t = threading.Thread(target=loop_forever, daemon=True, name="revenue-loop")
    t.start()
    return t


def get_log():
    """Return recent log entries."""
    return LOG[-50:]
