"""
Moduł pobierania oficjalnych komunikatów z Ministerstwa Finansów (gov.pl),
Zakładu Ubezpieczeń Społecznych (zus.pl) oraz kanałów podatkowych (RSS).
Pobiera pełne treści artykułów, nie same tytuły.
"""

import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import extract_article_body, fetch_text
from scripts.sources.rss_utils import fetch_rss_with_bodies, stable_item_id


POLISH_MONTHS = {
    "stycznia": "01",
    "lutego": "02",
    "marca": "03",
    "kwietnia": "04",
    "maja": "05",
    "czerwca": "06",
    "lipca": "07",
    "sierpnia": "08",
    "września": "09",
    "października": "10",
    "listopada": "11",
    "grudnia": "12",
}


def parse_polish_date(text: str) -> str:
    """Konwertuje daty typu '10.11.2026' lub '22 października 2026' do RRRR-MM-DD."""
    m_dot = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", text)
    if m_dot:
        return f"{m_dot.group(3)}-{m_dot.group(2)}-{m_dot.group(1)}"

    m_words = re.search(r"\b(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})\b", text.lower())
    if m_words:
        day = int(m_words.group(1))
        month_name = m_words.group(2)
        year = m_words.group(3)
        if month_name in POLISH_MONTHS:
            return f"{year}-{POLISH_MONTHS[month_name]}-{day:02d}"
    return ""


def parse_gov_finanse_list(list_html: str, base_url: str = "https://www.gov.pl", limit: int = 5) -> List[Dict[str, str]]:
    """Wyciąga listę najnowszych komunikatów z sekcji art-prev portalu gov.pl."""
    idx = list_html.find("art-prev")
    snippet = list_html[idx:] if idx != -1 else list_html
    pattern = re.compile(
        r'<span class="date">\s*(\d{2}\.\d{2}\.\d{4})\s*</span>.*?'
        r'<div class="title">\s*<a href="([^"]+)">(.*?)</a>',
        re.DOTALL,
    )
    items: List[Dict[str, str]] = []
    for date_str, href, raw_title in pattern.findall(snippet):
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw_title))).strip()
        full_url = href if href.startswith("http") else f"{base_url.rstrip('/')}{href}"
        items.append({
            "title": title,
            "url": full_url,
            "published": parse_polish_date(date_str),
        })
        if len(items) >= limit:
            break
    return items


def parse_zus_aktualnosci_list(list_html: str, limit: int = 5) -> List[Dict[str, str]]:
    """Wyciąga linki i tytuły aktualności z głównej listy zus.pl."""
    pattern = re.compile(
        r'href="(https://www\.zus\.pl/-/[^"]+\?redirect=%2Fo-zus%2Faktualnosci)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    seen_urls: Set[str] = set()
    items: List[Dict[str, str]] = []
    for raw_url, raw_title in pattern.findall(list_html):
        clean_url = raw_url.split("?")[0]
        if clean_url in seen_urls:
            continue
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw_title))).strip()
        if len(title) < 10:
            continue
        seen_urls.add(clean_url)
        items.append({
            "title": title,
            "url": clean_url,
            "published": "",
        })
        if len(items) >= limit:
            break
    return items


def fetch_zus_gov(config: Dict[str, Any], seen_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Pobiera najnowsze komunikaty z Ministerstwa Finansów, ZUS oraz kanałów podatkowych."""
    seen = seen_ids or set()
    max_items = int(config.get("max_items", 4))
    sources = config.get("sources", [])
    collected: List[Dict[str, Any]] = []
    errors: List[str] = []

    for src in sources:
        src_type = src.get("type", "")
        src_name = src.get("name", src.get("id", "gov_zus"))
        src_url = src.get("url", "")
        if not src_url:
            continue

        try:
            if src_type == "gov_html":
                html_page = fetch_text(src_url, timeout=10)
                entries = parse_gov_finanse_list(html_page, base_url=src.get("base_url", "https://www.gov.pl"), limit=4)
                for entry in entries:
                    item_id = stable_item_id("gov", entry["url"])
                    if item_id in seen:
                        continue
                    time.sleep(0.25)
                    article_html = fetch_text(entry["url"], timeout=10)
                    body = extract_article_body(article_html, max_chars=4500)
                    if len(body) < 120:
                        continue
                    collected.append({
                        "id": item_id,
                        "raw_title": entry["title"],
                        "published": entry["published"],
                        "full_text": f"Tytuł: {entry['title']}\nŹródło: {src_name}\nData: {entry['published']}\n\n{body}",
                        "url": entry["url"],
                        "source_name": src_name,
                        "section_id": "podatki_zus",
                    })
            elif src_type == "zus_html":
                html_page = fetch_text(src_url, timeout=12)
                entries = parse_zus_aktualnosci_list(html_page, limit=4)
                for entry in entries:
                    item_id = stable_item_id("zus", entry["url"])
                    if item_id in seen:
                        continue
                    time.sleep(0.25)
                    article_html = fetch_text(entry["url"], timeout=12)
                    idx = article_html.find("journal-content-article")
                    date_snippet = article_html[idx:idx + 500] if idx != -1 else article_html[:2000]
                    pub_date = parse_polish_date(re.sub(r"<[^>]+>", " ", date_snippet))
                    body = extract_article_body(article_html, max_chars=4500)
                    if len(body) < 120:
                        continue
                    collected.append({
                        "id": item_id,
                        "raw_title": entry["title"],
                        "published": pub_date,
                        "full_text": f"Tytuł: {entry['title']}\nŹródło: {src_name}\nData: {pub_date}\n\n{body}",
                        "url": entry["url"],
                        "source_name": src_name,
                        "section_id": "podatki_zus",
                    })
            elif src_type == "rss":
                rss_items = fetch_rss_with_bodies(
                    feed_url=src_url,
                    source_name=src_name,
                    section_id="podatki_zus",
                    prefix="tax",
                    limit=4,
                    max_body_chars=3500,
                )
                for it in rss_items:
                    if it["id"] not in seen:
                        collected.append(it)
        except Exception as exc:
            errors.append(f"{src_name}: {exc}")

        if len(collected) >= max_items * 2:
            break

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
            {"id": "mf_gov", "name": "Ministerstwo Finansów (gov.pl)", "type": "gov_html", "url": "https://www.gov.pl/web/finanse/wiadomosci"},
            {"id": "zus_pl", "name": "ZUS Aktualności (zus.pl)", "type": "zus_html", "url": "https://www.zus.pl/o-zus/aktualnosci"},
            {"id": "interia_podatki", "name": "Interia Biznes - Podatki", "type": "rss", "url": "https://biznes.interia.pl/podatki/feed"},
        ],
    }
    res = fetch_zus_gov(test_cfg)
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
