"""
Moduł pobierania wiadomości ze świata i gospodarki z kanałów RSS.
Pobiera fragment treści artykułu wyłącznie jako kontekst do streszczenia AI,
a do aplikacji trafiają wyłącznie własne streszczenie i link do oryginału.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.rss_utils import fetch_rss_with_bodies


def fetch_economy_world(config: Dict[str, Any], seen_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Pobiera aktualności gospodarcze i ze świata z listy źródeł RSS w konfiguracji."""
    seen = seen_ids or set()
    sources = config.get("sources", [])
    collected: List[Dict[str, Any]] = []
    errors: List[str] = []

    for src in sources:
        src_name = src.get("name", src.get("id", "RSS"))
        src_url = src.get("url", "")
        if not src_url:
            continue

        try:
            items = fetch_rss_with_bodies(
                feed_url=src_url,
                source_name=src_name,
                section_id="gospodarka_swiat",
                prefix="eco",
                limit=4,
                max_body_chars=2500,
                fetch_full_page=True,
            )
            for it in items:
                if it["id"] not in seen:
                    collected.append(it)
        except Exception as exc:
            errors.append(f"{src_name}: {exc}")

    status = "ok" if not errors else ("partial" if collected else "unavailable")
    return {
        "status": status,
        "error": "; ".join(errors) if errors else "",
        "items": collected,
    }


if __name__ == "__main__":
    test_cfg = {
        "max_items": 4,
        "sources": [
            {"id": "money_pl", "name": "Money.pl Wiadomości", "url": "https://www.money.pl/rss/wiadomosci.xml"},
            {"id": "bankier_pl", "name": "Bankier.pl Biznes", "url": "https://www.bankier.pl/rss/wiadomosci.xml"},
            {"id": "tvn24_swiat", "name": "TVN24 Najnowsze", "url": "https://tvn24.pl/najnowsze.xml"},
        ],
    }
    res = fetch_economy_world(test_cfg)
    print(json.dumps({
        "status": res["status"],
        "error": res.get("error"),
        "count": len(res["items"]),
        "sample": [
            {
                "id": it["id"],
                "source_name": it["source_name"],
                "published": it["published"],
                "raw_title": it["raw_title"][:85],
                "full_text_len": len(it["full_text"]),
            }
            for it in res["items"][:5]
        ],
    }, ensure_ascii=False, indent=2))
