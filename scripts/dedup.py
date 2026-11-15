"""
Moduł deduplikacji oraz selekcji najważniejszych pozycji (Zadanie 4).
Zapobiega powtarzaniu tych samych interpretacji i artykułów w kolejnych dniach.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Set


def load_seen_ids(seen_path: Path) -> Set[str]:
    """Wczytuje listę opublikowanych wcześniej identyfikatorów z pliku JSON."""
    if not seen_path.exists():
        return set()
    try:
        with open(seen_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(str(x) for x in data)
        if isinstance(data, dict):
            return set(str(x) for x in data.get("ids", []))
    except Exception:
        return set()
    return set()


def save_seen_ids(seen_path: Path, seen_ids: Set[str], new_ids: List[str], max_history: int = 2000) -> None:
    """Dopisuje nowe identyfikatory i zapisuje plik historii (z zachowaniem limitu)."""
    ordered = list(seen_ids)
    for nid in new_ids:
        if nid not in seen_ids:
            ordered.append(nid)
    if len(ordered) > max_history:
        ordered = ordered[-max_history:]
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    with open(seen_path, "w", encoding="utf-8") as f:
        json.dump({"ids": ordered}, f, ensure_ascii=False, indent=2)


def score_candidate(item: Dict[str, Any], priority_keywords: List[str], profile_tags: List[str]) -> int:
    """
    Oblicza punktację ważności kandydata według jawnych kryteriów:
    - obecność słów kluczowych (podatki, stawki, terminy, koszty, zmiany ustaw),
    - dopasowanie do priorytetowych tagów profilu firmy,
    - długość i kompletność pełnego tekstu źródłowego.
    """
    text_blob = (item.get("raw_title", "") + " " + item.get("full_text", "")[:1200]).lower()
    score = 0
    for kw in priority_keywords:
        if kw.lower() in text_blob:
            score += 3
    for tag in profile_tags:
        if tag.lower() in text_blob:
            score += 4
    if item.get("section_id") == "interpretacje":
        score += 5
    if len(item.get("full_text", "")) >= 1000:
        score += 2
    return score


def select_top_candidates(
    candidates: List[Dict[str, Any]],
    seen_ids: Set[str],
    max_items: int,
    priority_keywords: List[str],
    profile_tags: List[str],
) -> List[Dict[str, Any]]:
    """Odfiltrowuje duplikaty i wybiera najwyżej punktowane pozycje do limitu."""
    unique: List[Dict[str, Any]] = []
    local_seen: Set[str] = set(seen_ids)

    for cand in candidates:
        cid = str(cand.get("id", ""))
        if not cid or cid in local_seen:
            continue
        local_seen.add(cid)
        unique.append(cand)

    ranked = sorted(
        unique,
        key=lambda x: (
            score_candidate(x, priority_keywords, profile_tags),
            str(x.get("published", "")),
        ),
        reverse=True,
    )
    return ranked[:max_items]
