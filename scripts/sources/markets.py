"""
Moduł kursów walut i stóp procentowych NBP.
Wszystkie liczby pochodzą wyłącznie z oficjalnych API/XML NBP bez udziału AI.
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import fetch_json, fetch_text


def parse_nbp_table_a(payload: List[Dict[str, Any]], target_currencies: List[str]) -> Dict[str, Any]:
    """Parsuje JSON z Tabeli A NBP i wybiera wskazane waluty."""
    if not payload or not isinstance(payload, list):
        raise ValueError("Nieoczekiwana struktura odpowiedzi Tabeli A NBP")

    table = payload[0]
    wanted = set(c.upper() for c in target_currencies)
    rates = []
    for entry in table.get("rates", []):
        code = str(entry.get("code", "")).upper()
        if code in wanted:
            rates.append({
                "code": code,
                "currency": entry.get("currency", code),
                "mid": round(float(entry["mid"]), 4),
            })

    # Zachowaj kolejność z konfiguracji
    order = {c.upper(): idx for idx, c in enumerate(target_currencies)}
    rates.sort(key=lambda r: order.get(r["code"], 99))

    return {
        "table_no": table.get("no", ""),
        "effective_date": table.get("effectiveDate", ""),
        "rates": rates,
    }


def parse_nbp_reference_rate_xml(xml_content: str) -> Optional[Dict[str, Any]]:
    """Parsuje XML stóp procentowych NBP i wyciąga stopę referencyjną."""
    clean_xml = xml_content.lstrip("\ufeff").strip()
    root = ET.fromstring(clean_xml)
    for pos in root.findall(".//pozycja"):
        if pos.attrib.get("id") == "ref":
            raw_val = pos.attrib.get("oprocentowanie", "").replace(",", ".")
            return {
                "name": pos.attrib.get("nazwa", "Stopa referencyjna NBP"),
                "value_pct": float(raw_val),
                "effective_from": pos.attrib.get("obowiazuje_od", ""),
            }
    return None


def fetch_markets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pobiera kursy walut oraz stopę referencyjną NBP."""
    currencies = config.get("currencies", ["EUR", "USD", "CHF", "GBP"])
    table_url = config.get("nbp_table_a_url", "https://api.nbp.pl/api/exchangerates/tables/A/?format=json")
    rates_xml_url = config.get("nbp_rates_xml_url", "https://static.nbp.pl/dane/stopy/stopy_procentowe.xml")

    result: Dict[str, Any] = {
        "status": "ok",
        "table_no": "",
        "effective_date": "",
        "rates": [],
        "reference_rate": None,
        "source_url": "https://nbp.pl/statystyka-i-sprawozdawczosc/kursy/",
    }
    errors: List[str] = []

    try:
        table_json = fetch_json(table_url, timeout=10)
        parsed_table = parse_nbp_table_a(table_json, currencies)
        result.update(parsed_table)
    except Exception as exc:
        errors.append(f"Tabela A NBP: {exc}")

    try:
        xml_text = fetch_text(rates_xml_url, timeout=10)
        result["reference_rate"] = parse_nbp_reference_rate_xml(xml_text)
    except Exception as exc:
        errors.append(f"Stopy NBP: {exc}")

    if errors:
        result["error"] = "; ".join(errors)
        result["status"] = "partial" if result["rates"] or result["reference_rate"] else "unavailable"

    return result


if __name__ == "__main__":
    print(json.dumps(fetch_markets({"currencies": ["EUR", "USD", "CHF", "GBP"]}), ensure_ascii=False, indent=2))
