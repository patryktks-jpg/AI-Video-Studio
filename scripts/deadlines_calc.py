"""
Programowy kalkulator terminów podatkowych i ZUS (Zadanie 10).
Nie używa AI. Wylicza nadchodzące terminy na podstawie zweryfikowanego pliku
config/tax_deadlines.json z przesunięciem z weekendów i polskich świąt ustawowych
na najbliższy dzień roboczy (zgodnie z Ordynacją podatkową).
"""

import calendar
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _easter_sunday(year: int) -> datetime.date:
    """Oblicza datę Niedzieli Wielkanocnej (algorytm Meeusa/Butchera)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def polish_public_holidays(year: int) -> Set[datetime.date]:
    """Zwraca zbiór polskich świąt ustawowo wolnych od pracy w danym roku."""
    easter = _easter_sunday(year)
    holidays = {
        datetime.date(year, 1, 1),   # Nowy Rok
        datetime.date(year, 1, 6),   # Trzech Króli
        easter,                      # Wielkanoc
        easter + datetime.timedelta(days=1),   # Poniedziałek Wielkanocny
        datetime.date(year, 5, 1),   # Święto Pracy
        datetime.date(year, 5, 3),   # Święto Konstytucji 3 Maja
        easter + datetime.timedelta(days=49),  # Zesłanie Ducha Świętego
        easter + datetime.timedelta(days=60),  # Boże Ciało
        datetime.date(year, 8, 15),  # Wniebowzięcie NMP
        datetime.date(year, 11, 1),  # Wszystkich Świętych
        datetime.date(year, 11, 11), # Święto Niepodległości
        datetime.date(year, 12, 24), # Wigilia Bożego Narodzenia (od 2025 r.)
        datetime.date(year, 12, 25), # Pierwszy dzień Bożego Narodzenia
        datetime.date(year, 12, 26), # Drugi dzień Bożego Narodzenia
    }
    return holidays


def shift_to_business_day(target_date: datetime.date) -> datetime.date:
    """Przesuwa sobotę, niedzielę lub święto na następny dzień roboczy."""
    current = target_date
    holidays_cache: Dict[int, Set[datetime.date]] = {}
    while True:
        if current.year not in holidays_cache:
            holidays_cache[current.year] = polish_public_holidays(current.year)
        is_weekend = current.weekday() >= 5  # 5=sobota, 6=niedziela
        is_holiday = current in holidays_cache[current.year]
        if not is_weekend and not is_holiday:
            return current
        current += datetime.timedelta(days=1)


def compute_upcoming_deadlines(
    today: datetime.date,
    deadlines_config: Dict[str, Any],
    horizon_days: int = 7,
) -> List[Dict[str, Any]]:
    """
    Zwraca listę terminów przypadających w ciągu `horizon_days` dni od `today` (włącznie).
    Jeśli w oknie 7 dni nie ma żadnych terminów, automatycznie rozszerza do najbliższych
    nadchodzących terminów z horyzontu 14 dni, aby przedsiębiorca widział kolejny krok.
    """
    candidates: List[Dict[str, Any]] = []
    years_months = set()
    for delta in range(0, 32):
        d = today + datetime.timedelta(days=delta)
        years_months.add((d.year, d.month))

    # 1. Cykliczne terminy miesięczne
    for entry in deadlines_config.get("recurring_monthly", []):
        orig_day = int(entry["day"])
        for year, month in years_months:
            max_day = calendar.monthrange(year, month)[1]
            raw_date = datetime.date(year, month, min(orig_day, max_day))
            effective_date = shift_to_business_day(raw_date) if entry.get("shift_holiday", True) else raw_date
            diff = (effective_date - today).days
            if 0 <= diff <= 30:
                candidates.append({
                    "id": f"{entry['id']}-{effective_date.isoformat()}",
                    "date": effective_date.isoformat(),
                    "original_day": orig_day,
                    "shifted": effective_date != raw_date,
                    "days_remaining": diff,
                    "title": entry["title"],
                    "description": entry["description"],
                    "tags": entry.get("tags", []),
                })

    # 2. Terminy roczne
    for entry in deadlines_config.get("annual_special", []):
        month = int(entry["month"])
        orig_day = int(entry["day"])
        for year in {today.year, (today + datetime.timedelta(days=31)).year}:
            max_day = calendar.monthrange(year, month)[1]
            raw_date = datetime.date(year, month, min(orig_day, max_day))
            effective_date = shift_to_business_day(raw_date) if entry.get("shift_holiday", True) else raw_date
            diff = (effective_date - today).days
            if 0 <= diff <= 30:
                candidates.append({
                    "id": f"{entry['id']}-{effective_date.isoformat()}",
                    "date": effective_date.isoformat(),
                    "original_day": orig_day,
                    "shifted": effective_date != raw_date,
                    "days_remaining": diff,
                    "title": entry["title"],
                    "description": entry["description"],
                    "tags": entry.get("tags", []),
                })

    candidates.sort(key=lambda x: (x["days_remaining"], x["title"]))
    within_horizon = [c for c in candidates if c["days_remaining"] <= horizon_days]
    if within_horizon:
        return within_horizon
    return [c for c in candidates if c["days_remaining"] <= 14][:4]


def load_and_compute_deadlines(
    today: Optional[datetime.date] = None,
    config_path: Optional[Path] = None,
    horizon_days: int = 7,
) -> List[Dict[str, Any]]:
    """Wczytuje config/tax_deadlines.json i wylicza najbliższe terminy."""
    target_day = today or datetime.date.today()
    path = config_path or (Path(__file__).resolve().parents[1] / "config" / "tax_deadlines.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return compute_upcoming_deadlines(target_day, cfg, horizon_days=horizon_days)


def generate_ics_calendar(deadlines: List[Dict[str, Any]]) -> str:
    """Tworzy plik kalendarza .ics (RFC 5545) dla listy terminów."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Poranna Pigulka//Terminy Podatkowe//PL",
        "CALSCALE:GREGORIAN",
    ]
    for dl in deadlines:
        dt_str = dl["date"].replace("-", "")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{dl['id']}@poranna-pigulka.local",
            f"DTSTART;VALUE=DATE:{dt_str}",
            f"SUMMARY:{dl['title']}",
            f"DESCRIPTION:{dl['description']} (Zweryfikuj u księgowego)",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


if __name__ == "__main__":
    test_today = datetime.date(2026, 11, 15)
    upcoming = load_and_compute_deadlines(today=test_today, horizon_days=7)
    print(f"Terminy na 7 dni od {test_today}:")
    print(json.dumps(upcoming, ensure_ascii=False, indent=2))
