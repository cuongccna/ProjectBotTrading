#!/usr/bin/env python3
"""
Test Telegram Notification - Quick test to verify Telegram is working.

Usage:
    python scripts/test_telegram.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
from dotenv import load_dotenv
load_dotenv()


async def test_telegram():
    """Test Telegram notification."""
    import aiohttp
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    print("=" * 60)
    print("TELEGRAM NOTIFICATION TEST")
    print("=" * 60)
    print()
    
    # Check config
    print("📋 Configuration:")
    print(f"  TELEGRAM_BOT_TOKEN: {'✅ Set' if bot_token else '❌ Missing'}")
    if bot_token:
        print(f"    Token: {bot_token[:10]}...{bot_token[-5:]}")
    print(f"  TELEGRAM_CHAT_ID: {'✅ Set' if chat_id else '❌ Missing'}")
    if chat_id:
        print(f"    Chat ID: {chat_id}")
    print()
    
    if not bot_token or not chat_id:
        print("❌ Missing configuration! Check .env file.")
        return False
    
    # Test message
    test_message = """
🧪 <b>Telegram Test Message</b>

This is a test from your Crypto Trading Bot.

✅ If you see this, Telegram notifications are working!

📊 System Status: <code>OPERATIONAL</code>
🕐 Time: <code>{}</code>
    """.format(asyncio.get_event_loop().time())
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": test_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    
    print("📤 Sending test message...")
    print()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                result = await response.json()
                
                if response.status == 200 and result.get("ok"):
                    print("✅ SUCCESS! Message sent successfully!")
                    print()
                    print(f"  Message ID: {result.get('result', {}).get('message_id')}")
                    print("  Check your Telegram for the message.")
                    return True
                else:
                    print("❌ FAILED to send message!")
                    print()
                    print(f"  Status: {response.status}")
                    print(f"  Error: {result.get('description', 'Unknown error')}")
                    
                    # Common errors
                    error = result.get("description", "")
                    if "chat not found" in error.lower():
                        print()
                        print("💡 Hint: Make sure you've started a chat with your bot!")
                        print("   1. Find your bot on Telegram")
                        print("   2. Click 'Start' or send /start")
                        print("   3. Try again")
                    elif "unauthorized" in error.lower():
                        print()
                        print("💡 Hint: Your bot token is invalid!")
                        print("   Check TELEGRAM_BOT_TOKEN in .env")
                    
                    return False
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def get_chat_id():
    """Helper to get chat ID from recent messages."""
    import aiohttp
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    
    print("📥 Getting recent updates to find chat ID...")
    print()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                result = await response.json()
                
                if result.get("ok") and result.get("result"):
                    print("Recent chats:")
                    seen_chats = set()
                    for update in result["result"]:
                        chat = update.get("message", {}).get("chat", {})
                        chat_id = chat.get("id")
                        chat_type = chat.get("type")
                        title = chat.get("title") or chat.get("first_name", "Unknown")
                        
                        if chat_id and chat_id not in seen_chats:
                            seen_chats.add(chat_id)
                            print(f"  Chat ID: {chat_id}")
                            print(f"    Type: {chat_type}")
                            print(f"    Name: {title}")
                            print()
                    
                    if not seen_chats:
                        print("No recent messages found.")
                        print("Send /start to your bot first!")
                else:
                    print("No updates found.")
                    print("Send a message to your bot first!")
                    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Telegram notifications")
    parser.add_argument("--get-chat-id", action="store_true", 
                       help="Get chat ID from recent messages")
    args = parser.parse_args()
    
    if args.get_chat_id:
        asyncio.run(get_chat_id())
    else:
        success = asyncio.run(test_telegram())
        sys.exit(0 if success else 1)
