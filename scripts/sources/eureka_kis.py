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


EUREKA_BUSINESS_TERMS = (
    "działalność gospodarcz", "przedsiębiorc", "faktur", "koszt", "vat",
    "ryczałt", "usług", "handel", "b2b", "ksef", "jpk", "samochód",
    "ulga", "spółk", "odlicz", "stawk", "amortyzac", "najem", "leasing",
    "ip box", "podatek dochodowy",
)

EUREKA_EXCLUDE_TERMS = (
    "cmentarz", "spadek", "spadk", "zachowek", "bilet okresowy",
    "stosunek pracy", "alimenty", "osoba prywatna nieprowadząca",
    "zgonu", "zwłok", "pochówk",
)


def score_eureka_hit(hit: Dict[str, Any]) -> int:
    """Ocenia przydatność interpretacji dla przedsiębiorcy; zwraca -1 dla spraw prywatnych/obcych."""
    teza = str(hit.get("TEZA") or "").lower()
    kws = " ".join(str(k).lower() for k in (hit.get("SLOWA_KLUCZOWE") or []))
    blob = f"{teza} {kws}"
    if any(ex in blob for ex in EUREKA_EXCLUDE_TERMS):
        return -1
    score = 0
    for term in EUREKA_BUSINESS_TERMS:
        if term in blob:
            score += 2
    return score


def truncate_keeping_head_and_tail(text: str, max_chars: int) -> str:
    """Zachowuje stan faktyczny z początku oraz ocenę/uzasadnienie prawne organu z końca interpretacji."""
    if len(text) <= max_chars:
        return text
    marker = "\n\n[... pominięto środkową część dokumentu ...]\n\n"
    usable = max_chars - len(marker)
    if usable <= 400:
        return text[:max_chars]
    head_len = usable // 2
    tail_len = usable - head_len
    return text[:head_len].rstrip() + marker + text[-tail_len:].lstrip()


def fetch_eureka_interpretations(
    config: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None,
    max_source_chars: int = 12000,
) -> Dict[str, Any]:
    """
    Pobiera najnowsze interpretacje indywidualne z EUREKA MF, nadając priorytet tematom
    związanym z działalnością gospodarczą (VAT, ryczałt, koszty, B2B) i pomijając sprawy ściśle prywatne.
    """
    seen = seen_ids or set()
    search_base = config.get("search_url", "https://eureka.mf.gov.pl/api/public/v1/wyszukiwarka/informacje")
    detail_tpl = config.get("detail_url_template", "https://eureka.mf.gov.pl/api/public/v1/informacje/{id}")
    fetch_size = int(config.get("fetch_size", 25))
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

    ranked_hits = []
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

        hit_score = score_eureka_hit(hit)
        if hit_score < 0:
            continue

        pub_date = str(hit.get("DATA_PUBLIKACJI") or "")
        ranked_hits.append((hit_score, pub_date, hit))

    ranked_hits.sort(key=lambda x: (x[0], x[1]), reverse=True)

    collected: List[Dict[str, Any]] = []
    for _, _, hit in ranked_hits:
        info_id = str(hit.get("ID_INFORMACJI", "")).strip()
        try:
            time.sleep(delay)
            detail_url = detail_tpl.format(id=info_id)
            doc = fetch_json(detail_url, timeout=15)
            parsed = parse_eureka_document(doc, search_hit=hit)
            full_low = parsed["full_text"].lower()
            if any(ex in full_low for ex in ("pochówk", "cmentarz", "spadkobierc", "biletu okresowego")):
                continue
            parsed["full_text"] = truncate_keeping_head_and_tail(parsed["full_text"], max_source_chars)
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
