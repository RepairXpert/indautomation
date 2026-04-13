"""Process the cart recovery email queue.

Run this hourly via cron, UNO, or Windows Task Scheduler:
    python scripts/process_recovery_queue.py

It hits the /api/recovery/process endpoint on the live Render deployment.
Can also be pointed at localhost for testing.
"""
import json
import os
import sys
import urllib.request
import urllib.error

# Default to production
BASE_URL = os.environ.get("INDAUTO_URL", "https://indautomation.onrender.com")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    print("[RECOVERY] STRIPE_WEBHOOK_SECRET env var not set", file=sys.stderr)
    sys.exit(1)


def process_queue():
    """POST to /api/recovery/process with auth header."""
    url = f"{BASE_URL}/api/recovery/process"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Recovery-Key": WEBHOOK_SECRET,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            print(f"[RECOVERY] {result}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"[RECOVERY] HTTP {e.code}: {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[RECOVERY] Error: {e}", file=sys.stderr)
        return None


def check_stats():
    """GET /api/recovery/stats for monitoring."""
    url = f"{BASE_URL}/api/recovery/stats"
    req = urllib.request.Request(
        url,
        headers={"X-Recovery-Key": WEBHOOK_SECRET},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"[STATS] {json.dumps(result, indent=2)}")
            return result
    except Exception as e:
        print(f"[STATS] Error: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stats":
        check_stats()
    else:
        process_queue()
