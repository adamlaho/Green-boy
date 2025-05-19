#!/usr/bin/env python3
"""
Ultra Simple Telegram Webhook Cleanup

This script uses direct HTTP requests to properly clear any webhook 
and pending updates from the Telegram API.
"""
import os
import sys
import time
import requests
import json

# Get the bot token from environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN environment variable is not set")
    sys.exit(1)

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def main():
    # Step 1: Delete any webhook
    print(f"1. Deleting webhook...")
    response = requests.post(
        f"{API_BASE}/deleteWebhook",
        json={"drop_pending_updates": True}
    )
    
    if response.status_code == 200 and response.json().get("ok"):
        print("   ✓ Webhook deleted successfully")
    else:
        print(f"   ✗ Failed to delete webhook: {response.text}")
    
    # Step 2: Get information about the bot
    print(f"2. Getting bot info...")
    response = requests.get(f"{API_BASE}/getMe")
    
    if response.status_code == 200 and response.json().get("ok"):
        bot_info = response.json()["result"]
        print(f"   ✓ Connected to bot: @{bot_info['username']} (ID: {bot_info['id']})")
    else:
        print(f"   ✗ Failed to get bot info: {response.text}")
        sys.exit(1)
    
    # Step 3: Get updates to clear update queue
    print(f"3. Clearing update queue...")
    response = requests.post(
        f"{API_BASE}/getUpdates", 
        json={"offset": -1, "limit": 1, "timeout": 1}
    )
    
    if response.status_code == 200 and response.json().get("ok"):
        updates = response.json()["result"]
        if updates:
            last_update_id = updates[-1]["update_id"]
            print(f"   ✓ Found {len(updates)} pending updates, clearing...")
            
            # Clear updates by using offset = last_update_id + 1
            response = requests.post(
                f"{API_BASE}/getUpdates", 
                json={"offset": last_update_id + 1, "timeout": 1}
            )
            
            if response.status_code == 200 and response.json().get("ok"):
                print("   ✓ Update queue cleared successfully")
            else:
                print(f"   ✗ Failed to clear update queue: {response.text}")
        else:
            print("   ✓ No pending updates found")
    else:
        print(f"   ✗ Failed to get updates: {response.text}")
    
    # Step 4: Wait a moment to ensure Telegram's servers have processed everything
    print("4. Waiting for API state to settle (5 seconds)...")
    time.sleep(5)
    
    # Step 5: Final verification
    print("5. Verifying API state...")
    response = requests.post(
        f"{API_BASE}/getWebhookInfo"
    )
    
    if response.status_code == 200 and response.json().get("ok"):
        webhook_info = response.json()["result"]
        if webhook_info.get("url"):
            print(f"   ✗ WARNING: Webhook still set to: {webhook_info['url']}")
            print(f"     Trying one more time to delete webhook...")
            requests.post(f"{API_BASE}/deleteWebhook", json={"drop_pending_updates": True})
        else:
            print("   ✓ No webhook is set")
    else:
        print(f"   ✗ Failed to get webhook info: {response.text}")
    
    print("\nCleanup process completed.")
    print("=====================================")
    print("Wait at least 10 seconds before starting your bot.")
    print("If you still encounter conflicts, you may need to:")
    print("1. Wait longer (up to a few minutes)")
    print("2. Check for running processes: ps aux | grep python")
    print("3. Consider creating a new bot token with @BotFather")

if __name__ == "__main__":
    main()
