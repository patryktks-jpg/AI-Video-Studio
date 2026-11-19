"""
Moduł pobierania informacji legislacyjnych z otwartych API Sejmu RP oraz Dziennika Ustaw (ELI).
Priorytetowo pobiera druki i procesy sejmowe zawierające konkretne opisy zmian (co dokładnie się zmienia),
a przy aktach z Dziennika Ustaw wzbogaca treść o dyrektywy, komentarze artykułowe, opis procesu Sejmu
lub treść HTML aktu (z pominięciem pustych aktów bez treści ani związku z biznesem/podatkami).
"""

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import clean_html_to_text, fetch_json, fetch_text

BUSINESS_KEYWORDS = (
    "podat", "vat", "pit", "cit", "ryczałt", "ordynacj", "skarbow",
    "krajowej administracji skarbowej", "zus", "składk",
    "ubezpieczeń społecznych", "ubezpieczenia zdrowotnego",
    "przedsiębiorc", "działalności gospodarczej", "rachunkowośc",
    "faktur", "ksef", "akcyz", "kodeks pracy", "minimalnego wynagrodzenia",
    "deregulac", "celn",
)

EXCLUDED_KEYWORDS = (
    "krew", "krwi", "wody polskie", "rolnictwa", "obszarów wiejskich",
    "audiowizualn", "cmentarz", "łowieck", "leśn", "rybołówstw",
    "żeglug", "wojskow", "szkolnictw", "uczelni",
)


def is_business_relevant(text: str) -> bool:
    """Sprawdza, czy tytuł lub opis dotyczy biznesu/podatków/ZUS z wykluczeniem tematów branżowo obcych."""
    low = text.lower()
    if any(ex in low for ex in EXCLUDED_KEYWORDS):
        return False
    return any(kw in low for kw in BUSINESS_KEYWORDS)


def format_du_act_detail(
    act: Dict[str, Any],
    process_desc: str = "",
    html_excerpt: str = "",
) -> Dict[str, Any]:
    """Przekształca szczegóły aktu z ELI Dziennika Ustaw na bogaty rekord źródłowy."""
    display_addr = act.get("displayAddress", "")
    eli = act.get("ELI", "")
    title = act.get("title", "")
    promulgation = act.get("promulgation", "")
    entry_into_force = act.get("entryIntoForce", "brak danych")
    announcement = act.get("announcementDate", "")
    status = act.get("status", "")
    act_type = act.get("type", "")
    keywords = act.get("keywords", []) or []
    keywords_names = act.get("keywordsNames", []) or []
    released_by = act.get("releasedBy", []) or []
    obligated = act.get("obligated", []) or []
    comments = str(act.get("comments") or "").strip()
    directives = act.get("directives", []) or []

    released_str = ", ".join(str(r) for r in released_by) if released_by else "brak danych"
    all_kw = [str(k) for k in keywords] + [str(k) for k in keywords_names]
    keywords_str = ", ".join(dict.fromkeys(all_kw)) if all_kw else "brak"
    directives_str = "; ".join(
        f"{d.get('title', '')} ({d.get('address', '')})".strip()
        for d in directives
        if d.get("title") or d.get("address")
    )

    lines = [
        f"Akt prawny: {display_addr} ({act_type})",
        f"Tytuł aktu: {title}",
        f"Status obowiązywania: {status}",
        f"Data ogłoszenia (promulgacji): {promulgation}",
        f"Data wydania/podpisania: {announcement}",
        f"Data wejścia w życie: {entry_into_force}",
        f"Organ wydający: {released_str}",
        f"Słowa kluczowe ELI: {keywords_str}",
        f"Identyfikator ELI: {eli}",
    ]
    if obligated:
        lines.append(f"Podmioty zobowiązane: {', '.join(str(x) for x in obligated)}")
    if comments:
        lines.append(f"Szczegółowe terminy i uwagi wejścia w życie:\n{comments}")
    if directives_str:
        lines.append(f"Wdrażane dyrektywy UE / przedmiot zmian:\n{directives_str}")
    if process_desc:
        lines.append(f"Zakres zmian (opis z procesu legislacyjnego Sejmu):\n{process_desc}")
    if html_excerpt:
        lines.append(f"Treść aktu prawnego (fragment):\n{html_excerpt}")

    safe_id = eli.replace("/", "-").lower() if eli else f"du-{act.get('year')}-{act.get('pos')}"
    return {
        "id": f"eli-{safe_id}",
        "raw_title": f"{display_addr}: {title}",
        "published": promulgation or announcement,
        "full_text": "\n".join(lines),
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
    proc_title = ""
    if process_obj:
        proc_desc = str(process_obj.get("description") or "").strip()
        proc_title = str(process_obj.get("title") or "").strip()
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
        f"Tytuł projektu/dokumentu: {proc_title or title}\n"
        f"Szczegółowy dokument (druk): {title}\n"
        f"Data wpływu do Sejmu: {delivery}\n"
        f"Data dokumentu: {doc_date}\n"
        f"Status procesu: {passed_str}\n"
        f"Co projekt zmienia (opis merytoryczny Sejmu): {proc_desc or 'brak opisu w API'}\n"
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


def _build_prints_url(raw_url: str) -> str:
    """Upewnia się, że URL druków sejmowych pobiera najnowsze druki z limitem 100."""
    base = raw_url.split("?")[0]
    return f"{base}?sort_by=-deliveryDate&limit=100"


def fetch_legislation(
    config: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Pobiera najpierw merytoryczne procesy legislacyjne Sejmu (z opisem zmian),
    a następnie uzupełnia je aktami Dziennika Ustaw posiadającymi konkretny opis lub treść HTML.
    """
    seen = seen_ids or set()
    max_items = int(config.get("max_items", 4))
    current_year = datetime.date.today().year
    eli_list_url = config.get("eli_du_url_template", "https://api.sejm.gov.pl/eli/acts/DU/{year}").format(
        year=current_year
    )
    prints_url = _build_prints_url(
        config.get("sejm_prints_url", "https://api.sejm.gov.pl/sejm/term10/prints?sort_by=-deliveryDate&limit=100")
    )

    collected: List[Dict[str, Any]] = []
    errors: List[str] = []
    eli_to_process_desc: Dict[str, str] = {}
    checked_processes: Set[str] = set()

    # 1. Najpierw druki i procesy sejmowe (mają jasny opis merytoryczny 'description')
    try:
        all_prints = fetch_json(prints_url, timeout=15, allow_ssl_fallback=True)
        for pr in all_prints[:100]:
            title = str(pr.get("title", ""))
            if not is_business_relevant(title):
                continue
            num = str(pr.get("number", ""))
            term = pr.get("term", 10)
            proc_prints = pr.get("processPrint") or [num]
            proc_num = str(proc_prints[0])
            if proc_num in checked_processes:
                continue
            checked_processes.add(proc_num)

            proc_obj = None
            try:
                time.sleep(0.2)
                proc_obj = fetch_json(
                    f"https://api.sejm.gov.pl/sejm/term{term}/processes/{proc_num}",
                    timeout=10,
                    allow_ssl_fallback=True,
                )
            except Exception:
                proc_obj = None

            if not proc_obj:
                continue

            proc_desc = str(proc_obj.get("description") or "").strip()
            proc_eli = str(proc_obj.get("ELI") or "").strip()
            if proc_eli and proc_desc:
                eli_to_process_desc[proc_eli] = proc_desc

            item_id = f"sejm-druk-{term}-{num}"
            if item_id in seen:
                continue
            if not proc_desc:
                continue

            if len(collected) < max_items:
                collected.append(format_sejm_print(pr, proc_obj))
    except Exception as exc:
        errors.append(f"Sejm druki: {exc}")

    # 2. Dziennik Ustaw (ELI) - tylko akty z konkretną treścią (process_desc, dyrektywy lub textHTML)
    if len(collected) < max_items:
        try:
            du_data = fetch_json(eli_list_url, timeout=12, allow_ssl_fallback=True)
            du_items = du_data.get("items", [])[:35]
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
                    act_detail = fetch_json(
                        f"https://api.sejm.gov.pl/eli/acts/{eli}",
                        timeout=10,
                        allow_ssl_fallback=True,
                    )
                except Exception:
                    continue

                proc_desc = eli_to_process_desc.get(eli, "")
                html_excerpt = ""
                if act_detail.get("textHTML"):
                    try:
                        raw_html = fetch_text(
                            f"https://api.sejm.gov.pl/eli/acts/{eli}/text.html",
                            timeout=10,
                            allow_ssl_fallback=True,
                        )
                        html_excerpt = clean_html_to_text(raw_html)[:4000]
                    except Exception:
                        html_excerpt = ""

                has_directives = bool(act_detail.get("directives"))
                if not proc_desc and not html_excerpt and not has_directives:
                    # Pomijamy puste akty z samym tytułem i PDF-em bez treści tekstowej
                    continue

                collected.append(format_du_act_detail(act_detail, process_desc=proc_desc, html_excerpt=html_excerpt))
        except Exception as exc:
            errors.append(f"ELI Dziennik Ustaw: {exc}")

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
