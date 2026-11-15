"""
Dwuetapowy procesor AI (Zadanie 5):
- Etap A: ekstrakcja wyłącznie surowych faktów do JSON na podstawie pełnego tekstu źródłowego.
- Etap B: redakcja 3-poziomowego opracowania (headline, summary, details) wyłącznie na bazie faktów z Etapu A.
- Weryfikacja programowa liczb, dat i sygnatur względem tekstu źródłowego.
- Stała klauzula dla interpretacji KIS wpisana na sztywno w kodzie.
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.validator import verify_facts_against_source

KIS_MANDATORY_CAVEAT = (
    "Interpretacja indywidualna wiąże formalnie wyłącznie wnioskodawcę w jego indywidualnej sprawie, "
    "a dla pozostałych przedsiębiorców stanowi wskazówkę interpretacyjną pokazującą, jak organ rozumie przepisy."
)

GENERAL_LEGAL_CAVEAT = "Materiał ma charakter wyłącznie informacyjny i nie stanowi porady prawnej ani podatkowej."


def _load_prompt(filename: str) -> str:
    """Wczytuje plik promptu z katalogu /prompts."""
    path = Path(__file__).resolve().parents[1] / "prompts" / filename
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render_prompt(template: str, replacements: Dict[str, str]) -> str:
    """Bezpieczne podstawienie placeholderów bez kolizji z nawiasami klamrowymi schematów JSON."""
    out = template
    for key, val in replacements.items():
        out = out.replace("{" + key + "}", str(val))
    return out


class GeminiClient:
    """Klient REST Google Gemini API ze structured output (JSON), ponawianiem i kontrolą limitów."""

    def __init__(
        self,
        api_key: Optional[str],
        model_name: str = "gemini-3.5-flash-lite",
        fallback_models: Optional[List[str]] = None,
        delay_seconds: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.models = [model_name]
        for fb in (fallback_models or []):
            if fb not in self.models:
                self.models.append(fb)
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.calls_count = 0
        self.estimated_tokens = 0
        self._last_call_ts = 0.0

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "twoj_klucz_gemini_tutaj")

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call_ts
        if self._last_call_ts > 0 and elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def generate_json(self, prompt_text: str, temperature: float = 0.1) -> Optional[Dict[str, Any]]:
        """Wysyła zapytanie wymuszające odpowiedź w czystym JSON, z exponential backoff."""
        if not self.is_configured():
            return None

        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        for model in self.models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            for attempt in range(self.max_retries):
                self._throttle()
                req = urllib.request.Request(
                    url,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    self._last_call_ts = time.time()
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                    self.calls_count += 1
                    usage = res.get("usageMetadata", {})
                    self.estimated_tokens += int(usage.get("totalTokenCount", 0) or 0)

                    candidates = res.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        continue
                    raw_text = parts[0].get("text", "").strip()
                    return _parse_json_lenient(raw_text)
                except urllib.error.HTTPError as err:
                    code = err.code
                    if code in (429, 500, 503):
                        wait = (2 ** attempt) * 2.5
                        time.sleep(wait)
                        continue
                    if code == 404:
                        break  # Przejdź do następnego modelu fallbackowego
                    break
                except Exception:
                    wait = (2 ** attempt) * 1.5
                    time.sleep(wait)
        return None


def _parse_json_lenient(raw_text: str) -> Optional[Dict[str, Any]]:
    """Parsuje JSON nawet jeśli model otoczył go blokiem markdown ```json."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _deterministic_fallback_item(candidate: Dict[str, Any], reason_note: str) -> Dict[str, Any]:
    """
    Deterministyczny generator z pełnego tekstu źródłowego (bez zmyślania),
    używany w trybie bez klucza API lub po awarii limitów AI.
    """
    raw_title = str(candidate.get("raw_title", "Informacja")).strip()
    headline = raw_title[:87].rstrip() + "..." if len(raw_title) > 90 else raw_title
    full_text = str(candidate.get("full_text", ""))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", full_text) if len(s.strip()) > 30]
    summary = " ".join(sentences[:2])[:320] if sentences else raw_title
    if len(summary) < 15:
        summary = f"Opublikowano dokument źródłowy: {raw_title}."

    what_happened = "\n".join(sentences[:4])[:900] if sentences else summary
    section_id = candidate.get("section_id", "gospodarka_swiat")

    tags = []
    low = (raw_title + " " + full_text[:800]).lower()
    for tag, kws in [
        ("VAT", ("vat", "faktur", "paragon", "jpk")),
        ("PIT", ("pit", "ryczałt", "dochodow")),
        ("CIT", ("cit", "spółk")),
        ("ZUS", ("zus", "składk", "ubezpiecz", "zasił")),
        ("Ustawy", ("ustaw", "rozporządzen", "dz.u.", "sejm", "druk")),
        ("KSeF", ("ksef",)),
        ("Rynki", ("gpw", "nbp", "inflac", "walut", "gospodark")),
    ]:
        if any(k in low for k in kws):
            tags.append(tag)
    if not tags:
        tags = ["Rynki"] if section_id == "gospodarka_swiat" else ["Ustawy"]

    caveats = reason_note
    if section_id == "interpretacje":
        caveats = f"{KIS_MANDATORY_CAVEAT} {reason_note}".strip()

    return {
        "id": str(candidate.get("id")),
        "headline": headline,
        "summary": summary,
        "tags": tags[:3],
        "importance": "high" if section_id in ("interpretacje", "podatki_zus") else "medium",
        "relevance_for_profile": {
            "level": "medium",
            "reason": "Ocena wstępna na podstawie kategorii źródła (wymaga sprawdzenia szczegółów w linku).",
        },
        "details": {
            "what_happened": what_happened,
            "background": f"Materiał pochodzi z publikacji: {candidate.get('source_name', 'Źródło')}.",
            "what_it_means_for_business": "Zweryfikuj treść dokumentu źródłowego pod kątem zastosowania w Twojej działalności.",
            "what_to_do": ["Zapoznaj się z pełną treścią materiału w źródle poniżej."],
            "deadlines": [],
            "caveats": caveats,
        },
        "sources": [
            {
                "name": str(candidate.get("source_name", "Źródło")),
                "url": str(candidate.get("url", "")),
                "published": str(candidate.get("published", "")),
            }
        ],
        "confidence": "medium",
    }


def _normalize_synthesized_item(
    synth: Dict[str, Any],
    candidate: Dict[str, Any],
    confidence: str,
    mismatches: List[str],
) -> Dict[str, Any]:
    """Składa i ujednolica strukturę JSON pojedynczej pozycji pigułki."""
    headline = str(synth.get("headline") or candidate.get("raw_title") or "Aktualność").strip()
    if len(headline) > 105:
        headline = headline[:102].rstrip() + "..."
    if len(headline) < 5:
        headline = f"Info: {headline}"

    summary = str(synth.get("summary") or "").strip()
    if len(summary) < 15:
        summary = f"Opublikowano materiał: {headline}."

    tags = synth.get("tags") or []
    if not isinstance(tags, list) or not tags:
        tags = ["Ustawy"]
    tags = [str(t)[:24] for t in tags[:4]]

    importance = synth.get("importance", "medium")
    if importance not in ("high", "medium", "low"):
        importance = "medium"

    rel = synth.get("relevance_for_profile") or {}
    rel_level = rel.get("level", "medium")
    if rel_level not in ("high", "medium", "low", "none"):
        rel_level = "medium"
    rel_reason = str(rel.get("reason") or "Brak dodatkowego uzasadnienia.")

    raw_details = synth.get("details") or {}
    what_happened = str(raw_details.get("what_happened") or summary)
    background = str(raw_details.get("background") or "Brak dodatkowego kontekstu w źródle.")
    what_means = str(raw_details.get("what_it_means_for_business") or "Brak jednoznacznych wniosków w źródle.")

    what_to_do = raw_details.get("what_to_do") or []
    if not isinstance(what_to_do, list):
        what_to_do = [str(what_to_do)]
    what_to_do = [str(step) for step in what_to_do if str(step).strip()]

    deadlines = raw_details.get("deadlines") or []
    clean_deadlines = []
    if isinstance(deadlines, list):
        for dl in deadlines:
            if isinstance(dl, dict) and dl.get("date") and dl.get("description"):
                clean_deadlines.append({
                    "date": str(dl["date"]),
                    "description": str(dl["description"]),
                })

    caveats_parts = []
    if candidate.get("section_id") == "interpretacje":
        caveats_parts.append(KIS_MANDATORY_CAVEAT)
    if raw_details.get("caveats"):
        caveats_parts.append(str(raw_details["caveats"]).strip())
    if mismatches:
        caveats_parts.append("Ostrzeżenie weryfikacji automatycznej: " + " ".join(mismatches))
    caveats_parts.append(GENERAL_LEGAL_CAVEAT)

    return {
        "id": str(candidate.get("id")),
        "headline": headline,
        "summary": summary,
        "tags": tags,
        "importance": importance,
        "relevance_for_profile": {
            "level": rel_level,
            "reason": rel_reason,
        },
        "details": {
            "what_happened": what_happened,
            "background": background,
            "what_it_means_for_business": what_means,
            "what_to_do": what_to_do,
            "deadlines": clean_deadlines,
            "caveats": " ".join(caveats_parts).strip(),
        },
        "sources": [
            {
                "name": str(candidate.get("source_name", "Źródło")),
                "url": str(candidate.get("url", "")),
                "published": str(candidate.get("published", "")),
            }
        ],
        "confidence": confidence,
    }


def process_item_two_stage(
    client: GeminiClient,
    candidate: Dict[str, Any],
    company_profile: Dict[str, Any],
    section_title: str,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Przetwarza jedną pozycję w 2 etapach (A: fakty -> B: redakcja) wraz z weryfikacją.
    Zwraca (przetworzony_obiekt_lub_None, czy_odrzucono_przez_walidację).
    """
    if not client.is_configured():
        item = _deterministic_fallback_item(
            candidate,
            reason_note="Wygenerowano w trybie bez klucza API Gemini (opracowanie podstawowe).",
        )
        return item, False

    prompt_a_tpl = _load_prompt("stage_a_extract_facts.txt")
    prompt_b_tpl = _load_prompt("stage_b_write_synthesis.txt")

    source_text = str(candidate.get("full_text", ""))
    prompt_a = _render_prompt(prompt_a_tpl, {
        "section_title": section_title,
        "raw_title": str(candidate.get("raw_title", "")),
        "published": str(candidate.get("published", "")),
        "full_text": source_text,
    })

    facts = client.generate_json(prompt_a, temperature=0.0)
    if not facts:
        item = _deterministic_fallback_item(
            candidate,
            reason_note="Etap A ekstrakcji AI nie zwrócił poprawnego JSON; użyto streszczenia bazowego.",
        )
        return item, False

    profile_json_str = json.dumps(company_profile, ensure_ascii=False, indent=2)
    facts_json_str = json.dumps(facts, ensure_ascii=False, indent=2)
    prompt_b = _render_prompt(prompt_b_tpl, {
        "company_profile_json": profile_json_str,
        "facts_json": facts_json_str,
        "section_id": str(candidate.get("section_id", "")),
        "source_name": str(candidate.get("source_name", "")),
    })

    # Maksymalnie 2 próby dla Etapu B (regeneracja, jeśli program wykryje rozbieżność liczb/dat)
    for attempt in range(2):
        synth = client.generate_json(prompt_b, temperature=0.15 if attempt == 0 else 0.0)
        if not synth:
            continue
        candidate_item = _normalize_synthesized_item(synth, candidate, confidence="high", mismatches=[])
        confidence, mismatches = verify_facts_against_source(candidate_item, source_text)
        if confidence == "high":
            return candidate_item, False
        # Druga próba z obniżoną temperaturą, jeśli wykryto rozbieżności
        if attempt == 1:
            candidate_item = _normalize_synthesized_item(synth, candidate, confidence="low", mismatches=mismatches)
            return candidate_item, False

    item = _deterministic_fallback_item(
        candidate,
        reason_note="Etap B AI nie przeszedł weryfikacji; zastosowano bezpieczny opis ze źródła.",
    )
    item["confidence"] = "low"
    return item, True
