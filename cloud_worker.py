"""Cloud Worker — runs on Render/Railway cron, hits all service endpoints.
No local dependencies. Works 24/7 even when Eric's PC is off.

Deploy to Render as a cron job or background worker.
Schedule: every 30 minutes.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "")

SERVICES = {
    "indautomation": "https://indautomation.onrender.com/api/health",
    "clawgrab": "https://clawgrab.onrender.com/health",
    "debtclock": "https://us-debt-clock.onrender.com",
    "vendorad": "https://vendor-ad-network.onrender.com/health",
}

CART_RECOVERY = "https://indautomation.onrender.com/api/recovery/process"
RECOVERY_KEY = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def check_health(name, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CloudWorker/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"service": name, "status": "up", "code": resp.getcode()}
    except Exception as e:
        return {"service": name, "status": "down", "error": str(e)}


def process_cart_recovery():
    if not RECOVERY_KEY:
        return {"status": "no_key"}
    try:
        req = urllib.request.Request(
            CART_RECOVERY,
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Recovery-Key": RECOVERY_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_stripe():
    if not STRIPE_KEY:
        return {"status": "no_key"}
    try:
        req = urllib.request.Request(
            "https://api.stripe.com/v1/balance",
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            amt = data["available"][0]["amount"]
            return {"status": "ok", "balance_cents": amt}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    ts = datetime.now(timezone.utc).isoformat()
    print(f"=== Cloud Worker Cycle: {ts} ===")

    # Health checks
    for name, url in SERVICES.items():
        result = check_health(name, url)
        status = result["status"]
        print(f"  {name}: {status}")

    # Cart recovery
    recovery = process_cart_recovery()
    print(f"  cart_recovery: {recovery.get('status', '?')}")

    # Stripe balance
    stripe = check_stripe()
    if stripe.get("balance_cents"):
        print(f"  stripe: ${stripe['balance_cents']/100:.2f}")

    print(f"=== Done ===")


if __name__ == "__main__":
    main()
