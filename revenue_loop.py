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
        import base64
        auth = base64.b64encode(f"{STRIPE_KEY}:".encode()).decode()
        data = _http("https://api.stripe.com/v1/balance",
                      headers={"Authorization": f"Basic {auth}"})
        balance = data["available"][0]["amount"]

        pi_data = _http("https://api.stripe.com/v1/payment_intents?limit=5",
                         headers={"Authorization": f"Basic {auth}"})
        succeeded = [p for p in pi_data.get("data", []) if p["status"] == "succeeded"]

        log(f"Stripe: ${balance/100:.2f} balance, {len(succeeded)} recent payments")
        return {"balance": balance, "recent": len(succeeded)}
    except Exception as e:
        log(f"Stripe error: {e}")
        return {"balance": 0, "recent": 0}


def execute_task(task_description):
    """OpenCode-style: ask MiniMax to analyze a task and return executable actions.
    This gives the loop autonomous decision-making capability."""
    analysis = ask_minimax(
        f"You are an autonomous revenue agent for RepairXpertAI. "
        f"Analyze this task and return a JSON with 'actions' array. "
        f"Each action has 'type' (email/tweet/check/skip) and 'detail'. "
        f"Task: {task_description}"
    )
    if analysis:
        try:
            import re
            match = re.search(r'\{.*\}', analysis, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
    return None


def send_email_via_resend(to, subject, body):
    """Send email through Resend API — autonomous outreach capability."""
    if not RESEND_KEY:
        log("No Resend key — email skipped")
        return False
    try:
        _http("https://api.resend.com/emails", method="POST",
              data={"from": "RepairXpertAI <hello@repairxpertai.com>",
                    "to": [to], "subject": subject, "html": body},
              headers={"Authorization": f"Bearer {RESEND_KEY}"})
        log(f"Email sent: {to}")
        return True
    except Exception as e:
        log(f"Email failed ({to}): {e}")
        return False


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
    """One full revenue cycle — autonomous OpenCode-style execution."""
    log("=== REVENUE CYCLE START ===")

    # 1. Health check all services (keeps them warm)
    health = check_services()

    # 2. Check Stripe for new revenue
    stripe = check_stripe()
    if stripe["recent"] > 0:
        log(f"*** NEW REVENUE DETECTED: {stripe['recent']} payments ***")

    # 3. Process cart recovery
    process_cart_recovery()

    # 4. Ask MiniMax for analysis + executable action
    analysis = ask_minimax(
        f"You are RepairXpertAI's autonomous revenue agent running 24/7 in the cloud. "
        f"Stripe: ${stripe['balance']/100:.2f}. Services: {health}. "
        f"Products: IndAutomation $19/$99/mo, ClawGrab $12/mo, LITE $79, Crucix $29/$99. "
        f"93+ cold emails sent to industrial/HVAC/auto/building companies. 0 replies. "
        f"40+ tweets posted. 14 Dev.to articles. "
        f"What is the ONE most impactful thing to do RIGHT NOW? "
        f"Return JSON: {{\"action\": \"email|analyze|skip\", \"target\": \"...\", "
        f"\"subject\": \"...\", \"reason\": \"...\"}}. 50 words max."
    )
    if analysis:
        log(f"MiniMax: {analysis[:200]}")

        # 5. Auto-execute MiniMax's recommendation (OpenCode-style)
        task = execute_task(analysis)
        if task and task.get("actions"):
            for action in task["actions"][:3]:  # max 3 actions per cycle
                if action.get("type") == "email" and action.get("detail"):
                    detail = action["detail"]
                    if isinstance(detail, dict) and detail.get("to"):
                        send_email_via_resend(
                            detail["to"],
                            detail.get("subject", "RepairXpertAI — AI-Powered Fault Diagnosis"),
                            detail.get("body", f"<p>Check out <a href='https://indautomation.onrender.com'>IndAutomation</a></p>")
                        )
                elif action.get("type") == "skip":
                    log(f"MiniMax chose to skip: {action.get('detail', 'no reason')}")

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
