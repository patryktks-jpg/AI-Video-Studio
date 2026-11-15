"""
Wspólny moduł parsowania kanałów RSS i pobierania pełnej treści artykułów.
"""

import email.utils
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Dict, List

from scripts.sources.http_utils import extract_article_body, fetch_bytes, fetch_text


def normalize_pub_date(pub_date_raw: str) -> str:
    """Konwertuje datę RFC 2822 z RSS na format RRRR-MM-DD."""
    if not pub_date_raw:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_raw.strip())
        return dt.strftime("%Y-%m-%d")
    except Exception:
        m = re.search(r"\d{4}-\d{2}-\d{2}", pub_date_raw)
        return m.group(0) if m else pub_date_raw.strip()[:16]


def stable_item_id(prefix: str, url_or_title: str) -> str:
    """Tworzy stabilny, krótki identyfikator wpisu."""
    digest = hashlib.sha1(url_or_title.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def parse_rss_xml(xml_bytes: bytes, source_name: str, limit: int = 8) -> List[Dict[str, str]]:
    """Parsuje XML kanału RSS 2.0 i zwraca wstępne rekordy."""
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    nodes = channel.findall("item") if channel is not None else root.findall(".//item")

    results: List[Dict[str, str]] = []
    for node in nodes[:limit]:
        title = html.unescape(node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = html.unescape(node.findtext("description") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        pub_date = normalize_pub_date(node.findtext("pubDate") or "")
        if title and link:
            results.append({
                "title": title,
                "link": link,
                "description": desc,
                "published": pub_date,
                "source_name": source_name,
            })
    return results


def fetch_rss_with_bodies(
    feed_url: str,
    source_name: str,
    section_id: str,
    prefix: str,
    limit: int = 5,
    max_body_chars: int = 3500,
    fetch_full_page: bool = True,
) -> List[Dict[str, str]]:
    """Pobiera RSS i uzupełnia każdy wpis pełnym tekstem strony docelowej."""
    raw_bytes, _ = fetch_bytes(feed_url, timeout=10)
    entries = parse_rss_xml(raw_bytes, source_name=source_name, limit=limit)
    enriched: List[Dict[str, str]] = []

    for entry in entries:
        body_text = ""
        if fetch_full_page:
            try:
                page_html = fetch_text(entry["link"], timeout=8)
                body_text = extract_article_body(page_html, max_chars=max_body_chars)
            except Exception:
                body_text = ""

        combined_text = (
            f"Tytuł: {entry['title']}\n"
            f"Źródło: {source_name}\n"
            f"Data publikacji: {entry['published']}\n"
            f"Opis z kanału RSS: {entry['description']}\n"
        )
        if body_text:
            combined_text += f"\nTreść artykułu:\n{body_text}"

        enriched.append({
            "id": stable_item_id(prefix, entry["link"]),
            "raw_title": entry["title"],
            "published": entry["published"],
            "full_text": combined_text[:max_body_chars + 500],
            "url": entry["link"],
            "source_name": source_name,
            "section_id": section_id,
        })
    return enriched
