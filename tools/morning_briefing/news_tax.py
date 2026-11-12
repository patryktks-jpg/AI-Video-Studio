"""
Moduł pobierania wiadomości i zmian podatkowo-prawnych (News & Tax Module).
Wykorzystuje standardowe biblioteki Pythona (urllib, xml.etree.ElementTree).
Zawiera dedykowany scraper najnowszych interpretacji podatkowych KIS / MF.
"""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any


FEEDS = {
    "podatki_zus": [
        {"name": "Interia Podatki & Firma", "url": "https://biznes.interia.pl/podatki/feed"},
        {"name": "Money.pl Finanse & ZUS", "url": "https://www.money.pl/rss/wiadomosci.xml"},
    ],
    "ogolne": [
        {"name": "Bankier.pl Biznes", "url": "https://www.bankier.pl/rss/wiadomosci.xml"},
        {"name": "TVN24 Wiadomości", "url": "https://tvn24.pl/najnowsze.xml"},
    ],
}


def fetch_tax_interpretations(limit: int = 5) -> List[Dict[str, str]]:
    """
    Pobiera najświeższe interpretacje podatkowe i orzeczenia KIS/MF
    z dedykowanego serwisu podatki.biz/interpretacje/.
    """
    interpretations = []
    try:
        url = "https://www.podatki.biz/interpretacje/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            # Strona używa kodowania ISO-8859-2
            text = raw.decode("iso-8859-2", errors="replace")
            text = html.unescape(text)

        items = re.findall(r'<a\s+href="(/artykuly/[^"]+)"[^>]*>(.*?)</a>', text, re.DOTALL)
        seen = set()

        for link, raw_title in items:
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            # Odsiewamy krótkie linki nawigacyjne
            if len(clean_title) > 20 and clean_title not in seen:
                seen.add(clean_title)
                full_link = f"https://www.podatki.biz{link}"
                interpretations.append({
                    "title": clean_title,
                    "description": f"Nowa interpretacja / analiza skarbowa: {clean_title}",
                    "link": full_link,
                    "source": "Interpretacje KIS / Podatki.biz"
                })
                if len(interpretations) >= limit:
                    break
    except Exception as e:
        print(f"[Ostrzeżenie] Nie udało się pobrać interpretacji podatkowych: {e}")

    return interpretations


def fetch_rss_items(feed_url: str, limit: int = 5) -> List[Dict[str, str]]:
    """Pobiera i parsuje wpisy z kanału RSS."""
    items = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
        }
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        item_nodes = channel.findall("item") if channel is not None else root.findall(".//item")

        for item in item_nodes[:limit]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            description = item.findtext("description") or ""
            pub_date = item.findtext("pubDate") or ""

            clean_title = html.unescape(title).strip()
            clean_desc = html.unescape(description).strip()
            clean_desc = re.sub(r"<[^>]+>", "", clean_desc).strip()

            items.append({
                "title": clean_title,
                "description": clean_desc[:250] + ("..." if len(clean_desc) > 250 else ""),
                "link": link.strip(),
                "pub_date": pub_date.strip(),
            })
    except Exception as e:
        print(f"[Ostrzeżenie] Błąd podczas pobierania {feed_url}: {e}")

    return items


def get_latest_briefing_sources() -> Dict[str, Any]:
    """
    Agreguje surowe informacje:
    1. Interpretacje podatkowe KIS/MF
    2. Zmiany podatkowe i ZUS
    3. Ogólne wydarzenia z poprzedniego dnia
    """
    # 1. Świeże interpretacje podatkowe
    interpretations = fetch_tax_interpretations(limit=4)

    # 2. Artykuły podatkowo-zusowe
    tax_items = []
    for feed in FEEDS["podatki_zus"]:
        feed_items = fetch_rss_items(feed["url"], limit=5)
        for it in feed_items:
            it["source"] = feed["name"]
        tax_items.extend(feed_items)

    # 3. Ogólne newsy
    general_items = []
    for feed in FEEDS["ogolne"]:
        feed_items = fetch_rss_items(feed["url"], limit=4)
        for it in feed_items:
            it["source"] = feed["name"]
        general_items.extend(feed_items)

    return {
        "interpretations": interpretations,
        "tax_and_zus": tax_items,
        "general_news": general_items,
    }


if __name__ == "__main__":
    print("--- Test modułu pobierania wiadomości i interpretacji ---")
    data = get_latest_briefing_sources()
    print(f"Pobrano {len(data['interpretations'])} świeżych interpretacji podatkowych.")
    print(f"Pobrano {len(data['tax_and_zus'])} wpisów podatkowo-ZUS.")
    print(f"Pobrano {len(data['general_news'])} ogólnych wiadomości.")
    if data["interpretations"]:
        print("\nPrzykładowa interpretacja KIS:")
        print(f"• {data['interpretations'][0]['title']}\n  {data['interpretations'][0]['link']}")
