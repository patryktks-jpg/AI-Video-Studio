"""
Moduł wysyłki wiadomości do Telegrama (Telegram Sender).
Zawiera automatyczny fallback, jeśli w treści pojawią się znaki specjalne Markdown.
"""

import json
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Any


def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
    """
    Wysyła sformatowaną wiadomość tekstową na wskazany czat Telegrama.
    Jeśli parsowanie Markdown nie powiedzie się, automatycznie ponawia wysyłkę w trybie czystego tekstu.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    if len(text) > 4000:
        text = text[:3990] + "\n\n...(skrócono z uwagi na limit długości)"

    def _post(mode: str = None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if mode:
            payload["parse_mode"] = mode

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        res = _post(parse_mode)
        return {"success": True, "result": res}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        # Jeśli błąd wynika ze znaków Markdown lub encji, spróbuj wysłać jako plain text
        if "can't parse entities" in err_msg or "Bad Request" in err_msg and parse_mode:
            try:
                res = _post(mode=None)
                return {"success": True, "result": res}
            except Exception as e2:
                return {"success": False, "error": f"{err_msg} | Fallback err: {e2}"}
        return {"success": False, "error": err_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("--- Test modułu Telegram ---")
