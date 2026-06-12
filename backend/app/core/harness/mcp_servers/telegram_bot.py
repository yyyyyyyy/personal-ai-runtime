"""Telegram Bot MCP Server — send/receive messages via Telegram Bot API."""

import json
import os

from app.core.harness.url_safety import create_ssrf_safe_async_client


class TelegramBotServer:
    """Telegram Bot integration for messaging."""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> str:
        """Send a message via Telegram Bot."""
        if not self.token or not self.chat_id:
            return json.dumps({"error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured"})

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with create_ssrf_safe_async_client(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text[:4000],
                    "parse_mode": parse_mode,
                })
                data = resp.json()
                if data.get("ok"):
                    return json.dumps({"success": True, "message_id": data["result"]["message_id"]})
                return json.dumps({"error": data.get("description", "Unknown error")})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def get_me(self) -> str:
        """Get bot information."""
        if not self.token:
            return json.dumps({"error": "TELEGRAM_BOT_TOKEN not configured"})

        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            async with create_ssrf_safe_async_client(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("ok"):
                    return json.dumps({"bot": data["result"]})
                return json.dumps({"error": data.get("description", "Unknown error")})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def get_updates(self, limit: int = 5) -> str:
        """Get recent messages sent to the bot."""
        if not self.token:
            return json.dumps({"error": "TELEGRAM_BOT_TOKEN not configured"})

        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"limit": limit, "timeout": 5}
            async with create_ssrf_safe_async_client(timeout=10) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                if data.get("ok"):
                    updates = []
                    for update in data["result"]:
                        msg = update.get("message", {})
                        updates.append({
                            "from": msg.get("from", {}).get("first_name", "Unknown"),
                            "text": msg.get("text", ""),
                            "date": msg.get("date", 0),
                        })
                    return json.dumps({"count": len(updates), "updates": updates})
                return json.dumps({"error": data.get("description", "Unknown error")})
        except Exception as e:
            return json.dumps({"error": str(e)})


telegram_bot_server = TelegramBotServer()
