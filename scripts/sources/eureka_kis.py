"""
Moduł pobierania oficjalnych interpretacji indywidualnych z systemu EUREKA (Ministerstwo Finansów).
Korzysta z publicznego API wyszukiwarki i pobiera pełny tekst interpretacji (TRESC_INTERESARIUSZ),
zawierający opis stanu faktycznego, pytanie, stanowisko wnioskodawcy oraz ocenę organu.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import clean_html_to_text, fetch_json


def parse_eureka_document(doc: Dict[str, Any], search_hit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Wyciąga ustrukturyzowane metadane oraz pełną treść z dokumentu EUREKA."""
    fields_map: Dict[str, Any] = {}
    for field in doc.get("dokument", {}).get("fields", []):
        fields_map[field.get("key", "")] = field.get("value")

    info_id = str(fields_map.get("ID_INFORMACJI") or doc.get("id") or "")
    sygnatura = str(fields_map.get("SYG") or "brak sygnatury").strip()
    teza = str(fields_map.get("TEZA") or (search_hit or {}).get("TEZA") or "").strip()

    pub_raw = str(fields_map.get("DATA_PUBLIKACJI") or (search_hit or {}).get("DATA_PUBLIKACJI") or "")
    pub_date = pub_raw[:10] if len(pub_raw) >= 10 else pub_raw

    issue_raw = str(fields_map.get("DT_WYD") or (search_hit or {}).get("DT_WYD") or "")
    issue_date = issue_raw[:10] if len(issue_raw) >= 10 else issue_raw

    raw_html_body = str(fields_map.get("TRESC_INTERESARIUSZ") or "")
    clean_body = clean_html_to_text(raw_html_body)

    keywords = (search_hit or {}).get("SLOWA_KLUCZOWE") or []
    category_list = (search_hit or {}).get("KATEGORIA_INFORMACJI") or [doc.get("nazwa", "Interpretacja indywidualna")]
    category = category_list[0] if isinstance(category_list, list) and category_list else str(category_list)

    full_text = (
        f"Rodzaj dokumentu: {category}\n"
        f"Sygnatura: {sygnatura}\n"
        f"Data wydania: {issue_date}\n"
        f"Data publikacji w EUREKA: {pub_date}\n"
        f"Teza: {teza}\n"
        f"Słowa kluczowe: {', '.join(str(k) for k in keywords)}\n\n"
        f"Treść interpretacji:\n{clean_body}"
    )

    return {
        "id": f"kis-{info_id}",
        "raw_title": teza or f"Interpretacja indywidualna {sygnatura}",
        "signature": sygnatura,
        "published": pub_date,
        "issue_date": issue_date,
        "keywords": [str(k) for k in keywords],
        "full_text": full_text,
        "url": f"https://eureka.mf.gov.pl/informacje/podglad/{info_id}",
        "source_name": "EUREKA MF (KIS)",
        "section_id": "interpretacje",
    }


def fetch_eureka_interpretations(
    config: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None,
    max_source_chars: int = 8000,
) -> Dict[str, Any]:
    """
    Pobiera najnowsze interpretacje indywidualne z EUREKA MF.
    Pomija dokumenty już obecne w seen_ids i przestrzega odstępu między zapytaniami.
    """
    seen = seen_ids or set()
    search_base = config.get("search_url", "https://eureka.mf.gov.pl/api/public/v1/wyszukiwarka/informacje")
    detail_tpl = config.get("detail_url_template", "https://eureka.mf.gov.pl/api/public/v1/informacje/{id}")
    fetch_size = int(config.get("fetch_size", 10))
    max_items = int(config.get("max_items", 4))
    delay = float(config.get("request_delay_seconds", 0.6))

    search_url = f"{search_base}?size={fetch_size}&page=0&sort=DATA_PUBLIKACJI%2Cdesc"
    payload = {
        "filter": {},
        "columns": [
            "ID_INFORMACJI",
            "TEZA",
            "SYGNATURA",
            "DT_WYD",
            "DATA_PUBLIKACJI",
            "KATEGORIA_INFORMACJI",
            "SLOWA_KLUCZOWE",
        ],
        "searchInFullPhrase": False,
        "searchInContent": False,
        "searchInSynonyms": False,
        "searchQuery": "",
        "warunkiDodatkowe": [],
    }

    try:
        search_res = fetch_json(search_url, method="POST", payload=payload, timeout=15)
        hits = search_res.get("results", [])
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": f"EUREKA wyszukiwarka: {exc}",
            "items": [],
        }

    collected: List[Dict[str, Any]] = []
    for hit in hits:
        categories = hit.get("KATEGORIA_INFORMACJI") or []
        if not any("interpretacja" in str(c).lower() for c in categories):
            continue

        info_id = str(hit.get("ID_INFORMACJI", "")).strip()
        if not info_id:
            continue

        item_id = f"kis-{info_id}"
        if item_id in seen:
            continue

        try:
            time.sleep(delay)
            detail_url = detail_tpl.format(id=info_id)
            doc = fetch_json(detail_url, timeout=15)
            parsed = parse_eureka_document(doc, search_hit=hit)
            if len(parsed["full_text"]) > max_source_chars:
                parsed["full_text"] = parsed["full_text"][:max_source_chars]
            if len(parsed["full_text"]) >= 200:
                collected.append(parsed)
        except Exception as exc:
            # Awaria jednego dokumentu nie przerywa reszty
            print(f"[EUREKA] Pominięto ID {info_id}: {exc}", file=sys.stderr)
            continue

        if len(collected) >= max_items:
            break

    return {
        "status": "ok",
        "items": collected,
    }


if __name__ == "__main__":
    res = fetch_eureka_interpretations({"fetch_size": 5, "max_items": 2, "request_delay_seconds": 0.4})
    summary_res = {
        "status": res["status"],
        "count": len(res.get("items", [])),
        "sample": [
            {
                "id": it["id"],
                "signature": it["signature"],
                "published": it["published"],
                "raw_title": it["raw_title"],
                "full_text_len": len(it["full_text"]),
                "url": it["url"],
            }
            for it in res.get("items", [])
        ],
    }
    print(json.dumps(summary_res, ensure_ascii=False, indent=2))
