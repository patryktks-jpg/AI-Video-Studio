"""
Wspólne narzędzia HTTP, dekodowania polskich znaków i ekstrakcji pełnego tekstu z HTML.
Oparte w 100% na bibliotece standardowej Pythona.
"""

import html
import json
import re
import ssl
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple


USER_AGENT = "PorannaPigulkaBot/1.0 (+https://github.com/patryktks-jpg/AI-Video-Studio)"


class _ArticleParagraphParser(HTMLParser):
    """Wyciąga czysty tekst z elementów treściowych HTML (pomija nawigację, skrypty i stopkę)."""

    SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "svg"}
    BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_block = False
        self._current: List[str] = []
        self.paragraphs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._in_block = True
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS and self._in_block:
            text = re.sub(r"\s+", " ", "".join(self._current)).strip()
            if len(text) >= 25:
                self.paragraphs.append(text)
            self._in_block = False
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._in_block:
            self._current.append(data)


def clean_html_to_text(raw_html: str) -> str:
    """Konwertuje fragment HTML (np. treść interpretacji EUREKA) na czytelny tekst."""
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li|tr|h[1-6])[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_article_body(raw_html: str, max_chars: int = 5000) -> str:
    """Wyciąga główną treść artykułu z dokumentu HTML na podstawie bloków akapitowych."""
    snippet = raw_html
    for marker in ('class="journal-content-article', "<article", "<main"):
        idx = raw_html.find(marker)
        if idx != -1:
            snippet = raw_html[idx:]
            break

    parser = _ArticleParagraphParser()
    parser.feed(snippet)
    joined = "\n\n".join(parser.paragraphs)
    if not joined and snippet is not raw_html:
        parser = _ArticleParagraphParser()
        parser.feed(raw_html)
        joined = "\n\n".join(parser.paragraphs)
    if len(joined) > max_chars:
        return joined[:max_chars].rsplit(" ", 1)[0] + "..."
    return joined


def fetch_bytes(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 12,
    allow_ssl_fallback: bool = False,
) -> Tuple[bytes, Optional[str]]:
    """Wykonuje żądanie HTTP i zwraca (surowe_bajty, charset)."""
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)

    def _do_request(ctx: Optional[ssl.SSLContext]) -> Tuple[bytes, Optional[str]]:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read(), resp.headers.get_content_charset()

    try:
        return _do_request(ssl.create_default_context())
    except urllib.error.URLError as err:
        if allow_ssl_fallback and isinstance(err.reason, ssl.SSLError):
            insecure_ctx = ssl.create_default_context()
            insecure_ctx.check_hostname = False
            insecure_ctx.verify_mode = ssl.CERT_NONE
            return _do_request(insecure_ctx)
        raise


def fetch_text(
    url: str,
    timeout: int = 12,
    default_encoding: str = "utf-8",
    allow_ssl_fallback: bool = False,
) -> str:
    """Pobiera treść tekstową (HTML/XML) z automatycznym doborem kodowania."""
    raw, charset = fetch_bytes(url, timeout=timeout, allow_ssl_fallback=allow_ssl_fallback)
    enc = charset or default_encoding
    return raw.decode(enc, errors="replace")


def fetch_json(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 12,
    allow_ssl_fallback: bool = False,
) -> Any:
    """Pobiera i parsuje odpowiedź JSON."""
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    raw, charset = fetch_bytes(
        url,
        method=method,
        payload=payload,
        headers=req_headers,
        timeout=timeout,
        allow_ssl_fallback=allow_ssl_fallback,
    )
    return json.loads(raw.decode(charset or "utf-8"))
