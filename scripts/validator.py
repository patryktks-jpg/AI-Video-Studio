"""
Walidator struktury JSON oraz programowa weryfikacja faktów (liczb, dat, sygnatur)
w wygenerowanych opracowaniach względem oryginalnego tekstu źródłowego.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ALLOWED_WEATHER_STATUS = {"ok", "unavailable"}
ALLOWED_MARKET_STATUS = {"ok", "partial", "unavailable"}
ALLOWED_SECTION_STATUS = {"ok", "unavailable", "empty"}
ALLOWED_IMPORTANCE = {"high", "medium", "low"}
ALLOWED_RELEVANCE = {"high", "medium", "low", "none"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Wczytuje definicję JSON Schema z config/pill_schema.json."""
    path = schema_path or (Path(__file__).resolve().parents[1] / "config" / "pill_schema.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_pill_document(doc: Any) -> Tuple[bool, List[str]]:
    """
    Waliduje wyjściowy obiekt JSON pigułki względem reguł config/pill_schema.json.
    Zwraca (czy_poprawny, lista_błędów).
    """
    errors: List[str] = []
    if not isinstance(doc, dict):
        return False, ["Dokument główny musi być obiektem JSON."]

    for req_key in ("date", "generated_at", "weather", "markets", "deadlines", "sections"):
        if req_key not in doc:
            errors.append(f"Brak wymaganego pola głównego: '{req_key}'.")

    if isinstance(doc.get("date"), str):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", doc["date"]):
            errors.append("Pole 'date' musi mieć format RRRR-MM-DD.")
    elif "date" in doc:
        errors.append("Pole 'date' musi być ciągiem znaków.")

    weather = doc.get("weather")
    if isinstance(weather, dict):
        if "city" not in weather or not isinstance(weather["city"], str):
            errors.append("Pole 'weather.city' jest wymagane.")
        if weather.get("status") not in ALLOWED_WEATHER_STATUS:
            errors.append("Pole 'weather.status' ma niepoprawną wartość.")
    elif "weather" in doc:
        errors.append("Pole 'weather' musi być obiektem.")

    markets = doc.get("markets")
    if isinstance(markets, dict):
        if markets.get("status") not in ALLOWED_MARKET_STATUS:
            errors.append("Pole 'markets.status' ma niepoprawną wartość.")
    elif "markets" in doc:
        errors.append("Pole 'markets' musi być obiektem.")

    deadlines = doc.get("deadlines")
    if isinstance(deadlines, list):
        for idx, dl in enumerate(deadlines):
            if not isinstance(dl, dict):
                errors.append(f"deadlines[{idx}] musi być obiektem.")
                continue
            for k in ("id", "date", "title", "description", "tags"):
                if k not in dl:
                    errors.append(f"deadlines[{idx}] brak pola '{k}'.")
            if isinstance(dl.get("date"), str) and not re.match(r"^\d{4}-\d{2}-\d{2}$", dl["date"]):
                errors.append(f"deadlines[{idx}].date musi mieć format RRRR-MM-DD.")
    elif "deadlines" in doc:
        errors.append("Pole 'deadlines' musi być listą.")

    sections = doc.get("sections")
    if isinstance(sections, list):
        for s_idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                errors.append(f"sections[{s_idx}] musi być obiektem.")
                continue
            for k in ("id", "title", "status", "items"):
                if k not in sec:
                    errors.append(f"sections[{s_idx}] brak pola '{k}'.")
            if sec.get("status") not in ALLOWED_SECTION_STATUS:
                errors.append(f"sections[{s_idx}].status ma niepoprawną wartość.")
            items = sec.get("items")
            if not isinstance(items, list):
                errors.append(f"sections[{s_idx}].items musi być listą.")
                continue
            for i_idx, item in enumerate(items):
                _validate_item(item, f"sections[{s_idx}].items[{i_idx}]", errors)
    elif "sections" in doc:
        errors.append("Pole 'sections' musi być listą.")

    return len(errors) == 0, errors


def _validate_item(item: Any, prefix: str, errors: List[str]) -> None:
    """Waliduje pojedynczy wpis sekcji."""
    if not isinstance(item, dict):
        errors.append(f"{prefix} musi być obiektem.")
        return

    required = (
        "id", "headline", "summary", "tags", "importance",
        "relevance_for_profile", "details", "sources", "confidence"
    )
    for k in required:
        if k not in item:
            errors.append(f"{prefix} brak pola '{k}'.")

    headline = item.get("headline", "")
    if not isinstance(headline, str) or len(headline) < 5 or len(headline) > 110:
        errors.append(f"{prefix}.headline musi mieć od 5 do 110 znaków (obecnie {len(str(headline))}).")

    summary = item.get("summary", "")
    if not isinstance(summary, str) or len(summary) < 15:
        errors.append(f"{prefix}.summary jest zbyt krótkie lub brakujące.")

    if not isinstance(item.get("tags"), list):
        errors.append(f"{prefix}.tags musi być listą.")

    if item.get("importance") not in ALLOWED_IMPORTANCE:
        errors.append(f"{prefix}.importance ma niepoprawną wartość.")

    rel = item.get("relevance_for_profile")
    if isinstance(rel, dict):
        if rel.get("level") not in ALLOWED_RELEVANCE:
            errors.append(f"{prefix}.relevance_for_profile.level ma niepoprawną wartość.")
        if not isinstance(rel.get("reason"), str):
            errors.append(f"{prefix}.relevance_for_profile.reason musi być ciągiem znaków.")
    elif "relevance_for_profile" in item:
        errors.append(f"{prefix}.relevance_for_profile musi być obiektem.")

    details = item.get("details")
    if isinstance(details, dict):
        for dk in ("what_happened", "background", "what_it_means_for_business", "what_to_do", "deadlines", "caveats"):
            if dk not in details:
                errors.append(f"{prefix}.details brak pola '{dk}'.")
        if not isinstance(details.get("what_to_do"), list):
            errors.append(f"{prefix}.details.what_to_do musi być listą.")
        if not isinstance(details.get("deadlines"), list):
            errors.append(f"{prefix}.details.deadlines musi być listą.")
    elif "details" in item:
        errors.append(f"{prefix}.details musi być obiektem.")

    sources = item.get("sources")
    if not isinstance(sources, list) or len(sources) == 0:
        errors.append(f"{prefix}.sources musi zawierać co najmniej 1 źródło.")
    else:
        for s_idx, src in enumerate(sources):
            if not isinstance(src, dict) or not src.get("name") or not src.get("url"):
                errors.append(f"{prefix}.sources[{s_idx}] wymaga pól 'name' i 'url'.")

    if item.get("confidence") not in ALLOWED_CONFIDENCE:
        errors.append(f"{prefix}.confidence ma niepoprawną wartość.")


def _normalize_text_for_matching(text: str) -> str:
    """Normalizuje zapis liczb i dat do łatwego porównywania ze źródłem."""
    norm = text.lower().replace("\xa0", " ")
    # Zamień przecinek w liczbach dziesiętnych na kropkę (np. 8,5 -> 8.5)
    norm = re.sub(r"(\d),(\d)", r"\1.\2", norm)
    # Usuń spacje rozdzielające tysiące wewnątrz liczb (np. 1 500 -> 1500)
    norm = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", norm)
    return norm


def _date_variants(date_token: str) -> List[str]:
    """Generuje równoważne warianty zapisu daty (RRRR-MM-DD oraz DD.MM.RRRR)."""
    variants = [date_token.lower()]
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_token)
    if m_iso:
        y, m, d = m_iso.groups()
        variants.append(f"{d}.{m}.{y}")
        variants.append(f"{int(d)}.{int(m)}.{y}")
        return variants
    m_dot = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", date_token)
    if m_dot:
        d, m, y = m_dot.groups()
        variants.append(f"{y}-{m}-{d}")
    return variants


def verify_facts_against_source(item: Dict[str, Any], source_text: str) -> Tuple[str, List[str]]:
    """
    Sprawdza programowo, czy każda kluczowa liczba (z jednostką), data oraz sygnatura
    występująca w wygenerowanym opracowaniu pojawia się w oryginalnym tekście źródłowym.
    Zwraca (poziom_pewności, lista_rozbieżności).
    """
    details = item.get("details", {})
    generated_blob = " ".join([
        str(item.get("headline", "")),
        str(item.get("summary", "")),
        str(details.get("what_happened", "")),
        str(details.get("background", "")),
        str(details.get("what_it_means_for_business", "")),
    ])

    norm_source = _normalize_text_for_matching(source_text)
    norm_gen = _normalize_text_for_matching(generated_blob)
    mismatches: List[str] = []

    # 1. Sygnatury interpretacji KIS i Dz.U.
    signatures = re.findall(r"\b011\d-[a-z0-9.-]+\b", norm_gen, re.IGNORECASE)
    for sig in set(signatures):
        if sig.lower() not in norm_source:
            mismatches.append(f"Sygnatura '{sig}' nie została znaleziona w źródle.")

    du_refs = re.findall(r"dz\.?\s*u\.?\s*\d{4}\s*poz\.?\s*\d+", norm_gen, re.IGNORECASE)
    for ref in set(du_refs):
        num_match = re.findall(r"\d+", ref)
        if len(num_match) == 2:
            year, pos = num_match
            if pos not in norm_source or year not in norm_source:
                mismatches.append(f"Oznaczenie '{ref}' nie potwierdzone w źródle.")

    # 2. Daty ISO i kropkowe
    dates = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\b", norm_gen)
    for dt in set(dates):
        if not any(v in norm_source for v in _date_variants(dt)):
            mismatches.append(f"Data '{dt}' nie występuje w tekście źródłowym.")

    # 3. Wartości liczbowe z jednostkami
    num_tokens = re.findall(
        r"\b(\d+(?:\.\d+)?)\s*(%|proc\.?|tys\.?|zł|pln|eur|usd|chf|gbp|mln|mld)(?!\w)",
        norm_gen,
        re.IGNORECASE,
    )
    for num_val, unit in set(num_tokens):
        # Szukamy pełnej liczby (bez dopasowania fragmentu np. 19 wewnątrz 2019) w źródle
        stripped = num_val.rstrip("0").rstrip(".") if "." in num_val else num_val
        candidates = {num_val, stripped}
        matched = any(
            re.search(rf"(?<!\d){re.escape(c)}(?!\d)", norm_source)
            for c in candidates
            if c
        )
        if not matched:
            mismatches.append(f"Wartość '{num_val} {unit}' nie została znaleziona w tekście źródłowym.")

    if mismatches:
        return "low", mismatches
    return "high", []
