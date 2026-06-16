from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)

SOURCE_NAME = "favoritepokemon"
POKEDEX_URL = "https://favoritepokemon.vercel.app/#/pokedex"
STATS_URL = "https://favoritepokemon.vercel.app/#/stats"
SOURCE_URLS = (POKEDEX_URL, STATS_URL)


@dataclass
class ScrapedPage:
    source_url: str
    loaded_url: str
    title: str
    text_sample: str
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_path: Optional[str] = None


@dataclass
class FavoritePokemonScrapeResult:
    source_name: str
    source_urls: List[str]
    status: str
    rows: List[Dict[str, Any]]
    pages: List[ScrapedPage]
    notes: str

    def raw_payload(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_urls": self.source_urls,
            "status": self.status,
            "notes": self.notes,
            "rows": self.rows,
            "pages": [
                {
                    "source_url": page.source_url,
                    "loaded_url": page.loaded_url,
                    "title": page.title,
                    "text_sample": page.text_sample,
                    "candidates": page.candidates,
                    "screenshot_path": page.screenshot_path,
                }
                for page in self.pages
            ],
        }


class FavoritePokemonRenderedPageScraper:
    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def scrape(
        self,
        output_dir: Path,
        save_screenshots: bool = True,
    ) -> FavoritePokemonScrapeResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for favoritepokemon rendered-page scraping. "
                "Install backend requirements, then run: python -m playwright install chromium"
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        pages: List[ScrapedPage] = []
        all_rows: List[Dict[str, Any]] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            page = browser.new_page(
                user_agent="EVRCalculator-pokemon-desirability-snapshot/1.0"
            )

            for source_url in SOURCE_URLS:
                logger.info("Loading public rendered favoritepokemon page: %s", source_url)
                page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    logger.warning("Network idle timed out for %s; continuing with hydrated DOM snapshot", source_url)
                page.wait_for_timeout(1500)

                title = page.title()
                text = _visible_text(page.locator("body").inner_text(timeout=5000))
                candidates = _collect_visible_candidates(page)
                screenshot_path = None
                if save_screenshots:
                    screenshot_path = str(output_dir / _screenshot_name(source_url))
                    page.screenshot(path=screenshot_path, full_page=True)

                page_rows = extract_rows_from_candidates(candidates, source_url)
                if source_url == STATS_URL:
                    page_rows.extend(_collect_paginated_full_ranking_rows(page, source_url))
                all_rows.extend(page_rows)
                pages.append(
                    ScrapedPage(
                        source_url=source_url,
                        loaded_url=page.url,
                        title=title,
                        text_sample=text[:4000],
                        candidates=candidates[:300],
                        screenshot_path=screenshot_path,
                    )
                )

            browser.close()

        rows = _dedupe_rows(all_rows)
        status, notes = _status_for_rows(rows, pages)
        return FavoritePokemonScrapeResult(
            source_name=SOURCE_NAME,
            source_urls=list(SOURCE_URLS),
            status=status,
            rows=rows,
            pages=pages,
            notes=notes,
        )


def extract_rows_from_candidates(candidates: Iterable[Dict[str, Any]], source_url: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        text = _visible_text(candidate.get("text"))
        if not text or not _looks_like_pokemon_aggregate(text):
            continue
        ranking_rows = _parse_rank_vote_block(text, source_url, candidate)
        if ranking_rows:
            rows.extend(ranking_rows)
            continue
        row = _parse_candidate_text(text, source_url)
        if row:
            row["raw_row_json"] = {
                "text": text,
                "selector": candidate.get("selector"),
                "source_url": source_url,
            }
            rows.append(row)
    return rows


def _parse_rank_vote_block(text: str, source_url: str, candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "rank" not in text.casefold() or "votes" not in text.casefold():
        return []

    relevant_text = re.split(r"\bPrevious\b|\bNext\b", text, maxsplit=1, flags=re.I)[0]
    pattern = re.compile(
        r"#\s*(\d{1,4})\s+(.+?)\s+(\d[\d,]*)\s*(?=(?:#\s*\d{1,4}\s)|$)",
        flags=re.I,
    )
    rows: List[Dict[str, Any]] = []
    for match in pattern.finditer(relevant_text):
        rank = int(match.group(1))
        pokemon_name = _clean_ranked_name(match.group(2))
        vote_count = int(match.group(3).replace(",", ""))
        if not pokemon_name:
            continue
        rows.append(
            {
                "source_name": SOURCE_NAME,
                "pokemon_reference_id": None,
                "pokedex_number": None,
                "pokemon_name": pokemon_name,
                "raw_rank": rank,
                "raw_vote_count": vote_count,
                "raw_score": None,
                "raw_tier": None,
                "source_detail_url": source_url,
                "extraction_confidence": "high",
                "raw_row_json": {
                    "text": text,
                    "selector": candidate.get("selector"),
                    "source_url": source_url,
                    "rank_vote_block": True,
                },
            }
        )
    return rows


def _collect_paginated_full_ranking_rows(
    page: Any,
    source_url: str,
    max_pages: int = 110,
    delay_ms: int = 150,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_page_signatures = set()

    for page_index in range(max_pages):
        table_rows = _extract_full_ranking_table_rows(page, source_url)
        if not table_rows:
            break

        signature = tuple(
            (row.get("raw_rank"), row.get("pokemon_name"), row.get("raw_vote_count"))
            for row in table_rows
        )
        if signature in seen_page_signatures:
            break
        seen_page_signatures.add(signature)
        rows.extend(table_rows)

        next_button = page.get_by_role("button", name=re.compile(r"^Next$", re.I))
        if next_button.count() == 0:
            break
        next_control = next_button.first
        try:
            if next_control.is_disabled() or not next_control.is_visible():
                break
            next_control.click(timeout=3000)
            page.wait_for_timeout(delay_ms)
            page.wait_for_function(
                """
                ([previous]) => {
                  const rows = Array.from(document.querySelectorAll('table tr'))
                    .slice(1)
                    .map((row) => row.innerText.replace(/\\s+/g, ' ').trim())
                    .join('|');
                  return rows && rows !== previous;
                }
                """,
                arg=["|".join(_row_signature_text(row) for row in table_rows)],
                timeout=3000,
            )
        except Exception as exc:
            logger.info("Stopped full ranking pagination after page %s: %s", page_index + 1, exc)
            break

    if rows:
        logger.info("Collected %s row(s) from public full ranking pagination", len(rows))
    return rows


def _extract_full_ranking_table_rows(page: Any, source_url: str) -> List[Dict[str, Any]]:
    table = page.locator("table").first
    if table.count() == 0:
        return []

    try:
        header_text = _visible_text(table.locator("tr").first.inner_text(timeout=1000))
    except Exception:
        return []
    if "rank" not in header_text.casefold() or "votes" not in header_text.casefold():
        return []

    rows: List[Dict[str, Any]] = []
    tr_locator = table.locator("tr")
    for index in range(1, tr_locator.count()):
        try:
            text = _visible_text(tr_locator.nth(index).inner_text(timeout=1000))
        except Exception:
            continue
        parsed = _parse_table_row_text(text, source_url)
        if parsed:
            rows.append(parsed)
    return rows


def _parse_table_row_text(text: str, source_url: str) -> Optional[Dict[str, Any]]:
    match = re.match(r"^#\s*(\d{1,4})\s+(.+?)\s+(\d[\d,]*)$", text)
    if not match:
        return None

    pokemon_name = _clean_ranked_name(match.group(2))
    if not pokemon_name:
        return None

    return {
        "source_name": SOURCE_NAME,
        "pokemon_reference_id": None,
        "pokedex_number": None,
        "pokemon_name": pokemon_name,
        "raw_rank": int(match.group(1)),
        "raw_vote_count": int(match.group(3).replace(",", "")),
        "raw_score": None,
        "raw_tier": None,
        "source_detail_url": source_url,
        "extraction_confidence": "high",
        "raw_row_json": {
            "text": text,
            "selector": "table tr",
            "source_url": source_url,
            "full_ranking_table": True,
        },
    }


def _row_signature_text(row: Dict[str, Any]) -> str:
    return f"#{row.get('raw_rank')} {row.get('pokemon_name')} {row.get('raw_vote_count')}"


def _collect_visible_candidates(page: Any) -> List[Dict[str, Any]]:
    selectors = [
        "table tr",
        "[role='row']",
        "li",
        "article",
        "[class*='card' i]",
        "[class*='pokemon' i]",
        "[class*='rank' i]",
        "[class*='stat' i]",
        "section div",
    ]
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for selector in selectors:
        locator = page.locator(selector)
        count = min(locator.count(), 500)
        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible(timeout=500):
                    continue
                text = _visible_text(item.inner_text(timeout=1000))
            except Exception:
                continue
            if len(text) < 3 or text in seen:
                continue
            seen.add(text)
            candidates.append({"selector": selector, "text": text})
    return candidates


def _parse_candidate_text(text: str, source_url: str) -> Optional[Dict[str, Any]]:
    rank = _first_int_match(text, [
        r"(?:^|\s)#\s*(\d{1,4})(?:\s|$)",
        r"\brank(?:ed)?\s*#?\s*(\d{1,4})\b",
    ])
    pokedex_number = _first_int_match(text, [
        r"\bNo\.?\s*(\d{1,4})\b",
        r"\bDex\s*#?\s*(\d{1,4})\b",
        r"\b#\s*(\d{1,4})\b",
    ])
    vote_count = _first_int_match(text, [
        r"(\d[\d,]*)\s*(?:votes?|favorites?|favourites?|supporters?|declarations?)\b",
        r"(?:votes?|favorites?|favourites?|supporters?|declarations?)\s*[:#]?\s*(\d[\d,]*)\b",
    ])
    tier = _first_text_match(text, [
        r"\btier\s*[:#]?\s*([SABCDF])\b",
        r"\bstatus\s*[:#]?\s*([A-Za-z][A-Za-z ]{1,20})\b",
    ])
    pokemon_name = _extract_probable_name(text)

    if not pokemon_name:
        return None

    if rank is None and vote_count is None and tier is None:
        return None

    return {
        "source_name": SOURCE_NAME,
        "pokemon_reference_id": None,
        "pokedex_number": pokedex_number,
        "pokemon_name": pokemon_name,
        "raw_rank": rank,
        "raw_vote_count": vote_count,
        "raw_score": None,
        "raw_tier": tier,
        "source_detail_url": source_url,
        "extraction_confidence": "medium" if vote_count is not None or rank is not None else "low",
    }


def _extract_probable_name(text: str) -> Optional[str]:
    cleaned = re.sub(r"(?:^|\s)#\s*\d{1,4}\b", " ", text)
    cleaned = re.sub(r"\b(?:rank(?:ed)?|votes?|favorites?|favourites?|supporters?|declarations?|tier|status|dex|no)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\d[\d,]*", " ", cleaned)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    lines = [line.strip(":-#|") for line in lines if line.strip(":-#|")]
    if not lines:
        return None

    for line in lines:
        words = re.findall(r"[A-Za-z][A-Za-z'.:\- ]{1,40}", line)
        if words:
            name = " ".join(words[0].split())
            if 2 <= len(name) <= 40:
                return name
    return None


def _looks_like_pokemon_aggregate(text: str) -> bool:
    lowered = text.casefold()
    if "latest" in lowered and " chose " in lowered:
        return False
    if "declarations" in lowered and "unique pok" in lowered:
        return False
    if "final" in lowered and "chosen" in lowered and "complete the pok" in lowered:
        return False
    if "rank" in lowered and "votes" in lowered and re.search(r"#\s*\d{1,4}", text):
        return True
    has_signal = any(
        token in lowered
        for token in ("vote", "favorite", "favourite", "supporter", "declaration", "rank", "tier", "dex", "no.")
    )
    has_number = bool(re.search(r"\d", text))
    return has_signal and has_number


def _clean_ranked_name(value: str) -> Optional[str]:
    name = " ".join(str(value or "").split())
    name = re.sub(r"^(?:full ranking\s+)?rank\s+pok[eé]mon\s+votes\s+", "", name, flags=re.I)
    name = name.strip(":-#|")
    return name if 1 < len(name) <= 60 else None


def _dedupe_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("pokedex_number"),
            str(row.get("pokemon_name") or "").casefold(),
            row.get("raw_rank"),
            row.get("raw_vote_count"),
            row.get("raw_tier"),
        )
        by_key[key] = row
    return list(by_key.values())


def _status_for_rows(rows: List[Dict[str, Any]], pages: List[ScrapedPage]) -> tuple[str, str]:
    if not rows:
        return (
            "insufficient_data",
            "No visible public aggregate Pokemon vote, rank, or tier rows were extracted from rendered pages.",
        )
    if any(row.get("raw_vote_count") is not None for row in rows):
        return "captured_vote_counts", f"Extracted {len(rows)} visible aggregate row(s), including vote counts."
    if any(row.get("raw_rank") is not None for row in rows):
        return "captured_ranks", f"Extracted {len(rows)} visible aggregate ranked row(s)."
    return "captured_partial", f"Extracted {len(rows)} visible aggregate tier/status row(s)."


def _visible_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _first_int_match(text: str, patterns: Iterable[str]) -> Optional[int]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _first_text_match(text: str, patterns: Iterable[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return " ".join(match.group(1).split())
    return None


def _screenshot_name(source_url: str) -> str:
    suffix = "stats" if "stats" in source_url else "pokedex"
    return f"favoritepokemon_{suffix}_diagnostic.png"
