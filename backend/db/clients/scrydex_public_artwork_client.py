from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import requests

SCRYDEX_SITE_BASE = "https://scrydex.com"
_RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
_CARD_ID_RE = re.compile(r"/(me[^/?#]+)$", re.IGNORECASE)


class ScrydexPublicArtworkError(RuntimeError):
    pass


def _slugify_set_name(value: str) -> str:
    name = re.sub(
        r"^ME(?:\d+(?:\.\d+)?)?\s*:\s*",
        "",
        str(value or "").strip(),
        flags=re.IGNORECASE,
    )
    name = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return name


def _display_name_from_slug(value: str) -> str:
    name = unquote(str(value or "")).replace("-", " ")
    # Scrydex display slugs use Rayquaza-EX / Solgaleo-GX spellings while the
    # TCGplayer catalog generally stores Rayquaza EX / Solgaleo GX.
    return " ".join(name.split())


class _ScrydexCardAnchorParser(HTMLParser):
    def __init__(self, expected_set_id: str):
        super().__init__(convert_charrefs=True)
        self.expected_prefix = f"{expected_set_id}-".casefold()
        self.current: Optional[Dict[str, Any]] = None
        self.rows: Dict[str, Dict[str, Any]] = {}

    def handle_starttag(self, tag: str, attrs):
        if tag != "a" or self.current is not None:
            return
        data = dict(attrs)
        href = str(data.get("href") or "")
        if "/pokemon/cards/" not in href:
            return
        path = urlparse(href).path
        parts = [part for part in path.split("/") if part]
        if len(parts) < 4:
            return
        card_id = parts[-1]
        if not card_id.casefold().startswith(self.expected_prefix):
            return
        self.current = {
            "card_id": card_id,
            "slug": parts[-2],
            "text": [],
        }

    def handle_data(self, data: str):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag: str):
        if tag != "a" or self.current is None:
            return
        row = self.current
        self.current = None
        text = " ".join(" ".join(row["text"]).split())
        match = re.search(r"(.+?)\s*#\s*([A-Za-z0-9]+)", text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r"-(EX|GX|V|VMAX|VSTAR)$", r" \\1", name, flags=re.IGNORECASE)
            number = match.group(2).strip()
        else:
            name = _display_name_from_slug(row["slug"])
            suffix = row["card_id"].split("-", 1)[-1]
            number_match = re.match(r"(\d+)", suffix)
            number = number_match.group(1) if number_match else suffix
        existing = self.rows.get(row["card_id"])
        candidate = {
            "card_id": row["card_id"],
            "name": name,
            "number": number,
        }
        # Prefer an occurrence whose visible anchor text supplied both identity
        # fields over later image-only/table repetitions.
        if existing is None or (match and existing.get("_fallback")):
            candidate["_fallback"] = not bool(match)
            self.rows[row["card_id"]] = candidate


class ScrydexPublicArtworkClient:
    """One-request free fallback for artwork exposed on public Scrydex set pages.

    This does not scrape prices or analytics. It only reads the public card
    links already rendered on an expansion page and turns their Scrydex card IDs
    into the same public image CDN URLs that page itself uses.
    """

    def __init__(
        self,
        *,
        site_base: str = SCRYDEX_SITE_BASE,
        session: Optional[Any] = None,
        sleep=time.sleep,
    ) -> None:
        self.site_base = site_base.rstrip("/")
        self.session = session or requests.Session()
        self.sleep = sleep

    def _get_html(self, url: str) -> str:
        for attempt in range(1, 4):
            try:
                response = self.session.get(
                    url,
                    headers={"Accept": "text/html", "User-Agent": "EVRCalculator/1.0"},
                    timeout=(8.0, 45.0),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= 3:
                    raise ScrydexPublicArtworkError(
                        f"Scrydex public artwork request failed: {type(exc).__name__}"
                    ) from exc
                self.sleep(float(2 ** (attempt - 1)))
                continue

            if response.status_code in _RETRYABLE and attempt < 3:
                self.sleep(float(2 ** (attempt - 1)))
                continue
            if response.status_code >= 400:
                raise ScrydexPublicArtworkError(
                    f"Scrydex public artwork request failed HTTP {response.status_code}"
                )
            return response.text

        raise ScrydexPublicArtworkError("Scrydex public artwork request exhausted retries")

    def fetch_image_cards_for_set(self, *, set_name: str, scrydex_set_id: str) -> List[Dict[str, Any]]:
        set_id = str(scrydex_set_id or "").strip()
        if not set_id:
            raise ScrydexPublicArtworkError("Scrydex public artwork requires a set id")
        slug = _slugify_set_name(set_name)
        url = f"{self.site_base}/pokemon/expansions/{slug}/{set_id}"
        parser = _ScrydexCardAnchorParser(set_id)
        parser.feed(self._get_html(url))
        rows = []
        for row in parser.rows.values():
            card_id = row["card_id"]
            rows.append({
                "pokemon_tcg_api_id": card_id,
                "provider": "scrydex_public_artwork",
                "set_id": set_id,
                "set_name": set_name,
                "number": row.get("number"),
                "name": row.get("name"),
                "image_small_url": f"https://images.scrydex.com/pokemon/{card_id}/small",
                "image_large_url": f"https://images.scrydex.com/pokemon/{card_id}/large",
            })
        if not rows:
            raise ScrydexPublicArtworkError(
                f"Scrydex public expansion page exposed no card artwork for {set_name!r}"
            )
        return sorted(rows, key=lambda row: str(row.get("pokemon_tcg_api_id") or ""))
