"""
Moduł pobierania informacji legislacyjnych z otwartych API Sejmu RP oraz Dziennika Ustaw (ELI).
Korzysta z:
- https://api.sejm.gov.pl/eli/acts/DU/{rok} (+ szczegóły aktu /DU/{rok}/{pos})
- https://api.sejm.gov.pl/sejm/term10/prints?sort_by=-deliveryDate (+ powiązany proces legislacyjny)
"""

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import fetch_json

BUSINESS_KEYWORDS = (
    "podat", "vat", "pit", "cit", "skarbow", "kas", "zus", "skład", "ubezpiecz",
    "przedsiębior", "gospodar", "finans", "rachunkow", "faktur", "ksef",
    "celn", "akcyz", "pracy", "płac", "deregulac", "działalnoś", "inwestyc",
    "płatnicz", "mikro", "mśp"
)


def is_business_relevant(text: str) -> bool:
    """Sprawdza, czy tytuł lub słowa kluczowe dotyczą tematyki biznesowej/podatkowej."""
    low = text.lower()
    return any(kw in low for kw in BUSINESS_KEYWORDS)


def format_du_act_detail(act: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca szczegóły aktu z ELI Dziennika Ustaw na ustandaryzowany rekord źródłowy."""
    display_addr = act.get("displayAddress", "")
    eli = act.get("ELI", "")
    title = act.get("title", "")
    promulgation = act.get("promulgation", "")
    entry_into_force = act.get("entryIntoForce", "brak danych")
    announcement = act.get("announcementDate", "")
    status = act.get("status", "")
    act_type = act.get("type", "")
    keywords = act.get("keywords", []) or []
    released_by = act.get("releasedBy", []) or []

    released_str = ", ".join(str(r) for r in released_by) if released_by else "brak danych"
    keywords_str = ", ".join(str(k) for k in keywords) if keywords else "brak"

    full_text = (
        f"Akt prawny: {display_addr} ({act_type})\n"
        f"Tytuł aktu: {title}\n"
        f"Status obowiązywania: {status}\n"
        f"Data ogłoszenia (promulgacji): {promulgation}\n"
        f"Data wydania/podpisania: {announcement}\n"
        f"Data wejścia w życie: {entry_into_force}\n"
        f"Organ wydający: {released_str}\n"
        f"Słowa kluczowe ELI: {keywords_str}\n"
        f"Identyfikator ELI: {eli}"
    )

    safe_id = eli.replace("/", "-").lower() if eli else f"du-{act.get('year')}-{act.get('pos')}"
    return {
        "id": f"eli-{safe_id}",
        "raw_title": f"{display_addr}: {title}",
        "published": promulgation or announcement,
        "full_text": full_text,
        "url": f"https://eli.gov.pl/eli/{eli}/ogl" if eli else "https://dziennikustaw.gov.pl/",
        "source_name": "Dziennik Ustaw (ELI Sejm)",
        "section_id": "podatki_zus",
    }


def format_sejm_print(print_obj: Dict[str, Any], process_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Przekształca druk sejmowy i jego proces legislacyjny na ustandaryzowany rekord źródłowy."""
    num = str(print_obj.get("number", ""))
    title = str(print_obj.get("title", "")).strip()
    delivery = str(print_obj.get("deliveryDate", ""))
    doc_date = str(print_obj.get("documentDate", ""))
    term = print_obj.get("term", 10)

    stages_lines = []
    proc_desc = ""
    passed = None
    if process_obj:
        proc_desc = str(process_obj.get("description") or "").strip()
        passed = process_obj.get("passed")
        for st in process_obj.get("stages", [])[-5:]:
            st_date = st.get("date", "")
            st_name = st.get("stageName", "")
            if st_name:
                stages_lines.append(f"- {st_date}: {st_name}".strip())

    stages_text = "\n".join(stages_lines) if stages_lines else "Brak szczegółowych etapów w API."
    passed_str = "Uchwalony" if passed is True else ("W toku / nieuchwalony" if passed is False else "W trakcie prac")

    full_text = (
        f"Druk sejmowy nr {num} (Kadencja {term})\n"
        f"Tytuł projektu/dokumentu: {title}\n"
        f"Data wpływu do Sejmu: {delivery}\n"
        f"Data dokumentu: {doc_date}\n"
        f"Status procesu: {passed_str}\n"
        f"Opis z procesu Sejmu: {proc_desc or 'brak dodatkowego opisu w bazie API'}\n"
        f"Ostatnie etapy prac:\n{stages_text}"
    )

    return {
        "id": f"sejm-druk-{term}-{num}",
        "raw_title": f"Druk sejmowy nr {num}: {title}",
        "published": delivery or doc_date,
        "full_text": full_text,
        "url": f"https://www.sejm.gov.pl/Sejm{term}.nsf/PrzebiegProc.xsp?nr={num}",
        "source_name": "Sejm RP (API)",
        "section_id": "podatki_zus",
    }


def fetch_legislation(
    config: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Pobiera nowe akty z Dziennika Ustaw oraz biznesowe druki sejmowe."""
    seen = seen_ids or set()
    max_items = int(config.get("max_items", 4))
    current_year = datetime.date.today().year
    eli_list_url = config.get("eli_du_url_template", "https://api.sejm.gov.pl/eli/acts/DU/{year}").format(
        year=current_year
    )
    prints_url = config.get("sejm_prints_url", "https://api.sejm.gov.pl/sejm/term10/prints?sort_by=-deliveryDate")

    collected: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1. Dziennik Ustaw (ELI) - najnowsze 25 aktów, filtr biznesowy
    try:
        du_data = fetch_json(eli_list_url, timeout=12, allow_ssl_fallback=True)
        du_items = du_data.get("items", [])[:25]
        for item in du_items:
            if len(collected) >= max_items:
                break
            title = str(item.get("title", ""))
            if not is_business_relevant(title):
                continue
            eli = str(item.get("ELI", ""))
            safe_id = f"eli-{eli.replace('/', '-').lower()}"
            if safe_id in seen:
                continue
            try:
                time.sleep(0.25)
                act_detail = fetch_json(f"https://api.sejm.gov.pl/eli/acts/{eli}", timeout=10, allow_ssl_fallback=True)
                collected.append(format_du_act_detail(act_detail))
            except Exception:
                collected.append(format_du_act_detail(item))
    except Exception as exc:
        errors.append(f"ELI Dziennik Ustaw: {exc}")

    # 2. Druki sejmowe (sortowane od najnowszych)
    if len(collected) < max_items:
        try:
            if "sort_by=" not in prints_url:
                sep = "&" if "?" in prints_url else "?"
                prints_url = f"{prints_url}{sep}sort_by=-deliveryDate"
            all_prints = fetch_json(prints_url, timeout=15, allow_ssl_fallback=True)
            for pr in all_prints[:40]:
                if len(collected) >= max_items:
                    break
                title = str(pr.get("title", ""))
                if not is_business_relevant(title):
                    continue
                num = str(pr.get("number", ""))
                term = pr.get("term", 10)
                item_id = f"sejm-druk-{term}-{num}"
                if item_id in seen:
                    continue
                proc_obj = None
                proc_prints = pr.get("processPrint") or []
                if proc_prints:
                    try:
                        time.sleep(0.25)
                        proc_obj = fetch_json(
                            f"https://api.sejm.gov.pl/sejm/term{term}/processes/{proc_prints[0]}",
                            timeout=10,
                            allow_ssl_fallback=True,
                        )
                    except Exception:
                        proc_obj = None
                collected.append(format_sejm_print(pr, proc_obj))
        except Exception as exc:
            errors.append(f"Sejm druki: {exc}")

    status = "ok" if not errors else ("partial" if collected else "unavailable")
    return {
        "status": status,
        "error": "; ".join(errors) if errors else "",
        "items": collected,
    }


if __name__ == "__main__":
    res = fetch_legislation({"max_items": 3})
    summary = {
        "status": res["status"],
        "error": res.get("error"),
        "count": len(res.get("items", [])),
        "sample": [
            {
                "id": it["id"],
                "published": it["published"],
                "raw_title": it["raw_title"][:95],
                "full_text_len": len(it["full_text"]),
            }
            for it in res.get("items", [])
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
