import copy
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests


class RequestCapExceededError(RuntimeError):
    """Raised when run-level HTTP request cap is exceeded."""


class SustainedRateLimitError(RuntimeError):
    """Raised when rate-limit/challenge responses become sustained."""


class TCGPlayerClient:
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.tcgplayer.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
        self.session.headers.update(self.headers)

        self.request_delay_min = float(os.getenv("REQUEST_DELAY_MIN_SECONDS", "1.0"))
        self.request_delay_max = float(os.getenv("REQUEST_DELAY_MAX_SECONDS", "2.0"))
        if self.request_delay_max < self.request_delay_min:
            self.request_delay_max = self.request_delay_min

        self.max_requests_per_run = int(os.getenv("MAX_HTTP_REQUESTS_PER_RUN", "20000"))
        self.max_request_retries = int(os.getenv("HTTP_MAX_RETRIES", "4"))
        self.timeout_seconds = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))
        self.base_backoff_seconds = float(os.getenv("HTTP_BACKOFF_BASE_SECONDS", "2.0"))
        self.max_consecutive_rate_limits = int(os.getenv("MAX_CONSECUTIVE_RATE_LIMITS", "8"))

        self._request_cache: Dict[str, Any] = {}
        self._helper_seen_today: Dict[Tuple[str, str], bool] = {}
        self._today_utc = datetime.now(timezone.utc).date().isoformat()
        self._consecutive_rate_limit_events = 0

        self.metrics: Dict[str, Any] = {
            "http_requests_total": 0,
            "http_requests_cache_hits": 0,
            "http_requests_cache_misses": 0,
            "http_requests_skipped_redundant": 0,
            "rate_limit_events": 0,
            "retry_count_total": 0,
            "aborted_due_to_request_cap": False,
            "aborted_due_to_rate_limit": False,
        }

    def _request_key(self, method: str, url: str, payload: Optional[Dict[str, Any]]) -> str:
        body_key = ""
        if payload is not None:
            body_key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"{method.upper()}::{url}::{body_key}"

    def _is_helper_or_metadata_url(self, url: str) -> bool:
        lowered = (url or "").lower()
        helper_markers = (
            "search",
            "metadata",
            "index",
            "category",
            "navigation",
            "catalog",
            "discovery",
        )
        return any(marker in lowered for marker in helper_markers)

    def _jitter_sleep(self) -> None:
        time.sleep(random.uniform(self.request_delay_min, self.request_delay_max))

    def _backoff_sleep(self, attempt: int) -> None:
        delay = self.base_backoff_seconds * (2 ** (attempt - 1)) + random.uniform(0.0, 0.6)
        time.sleep(delay)

    def _check_request_cap(self) -> None:
        if self.metrics["http_requests_total"] >= self.max_requests_per_run:
            self.metrics["aborted_due_to_request_cap"] = True
            raise RequestCapExceededError(
                f"HTTP request cap exceeded ({self.max_requests_per_run})"
            )

    def _is_challenge_or_login_page(self, response: requests.Response) -> bool:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" not in content_type:
            return False

        text = (response.text or "").lower()
        suspicious_tokens = (
            "captcha",
            "verify you are human",
            "challenge",
            "cloudflare",
            "access denied",
            "rate limit",
            "login",
            "sign in",
        )
        return any(token in text for token in suspicious_tokens)

    def _record_rate_limit_event(self, reason: str, attempt: int, url: str) -> None:
        self.metrics["rate_limit_events"] += 1
        self._consecutive_rate_limit_events += 1
        print(
            f"[scraper-http] rate-limit/challenge event reason={reason} attempt={attempt} url={url}"
        )
        if self._consecutive_rate_limit_events >= self.max_consecutive_rate_limits:
            self.metrics["aborted_due_to_rate_limit"] = True
            raise SustainedRateLimitError(
                "Sustained rate-limit/challenge responses detected; aborting run early"
            )

    def _request_json(self, method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_key = self._request_key(method, url, payload)
        is_helper_request = self._is_helper_or_metadata_url(url)

        if request_key in self._request_cache:
            self.metrics["http_requests_cache_hits"] += 1
            self.metrics["http_requests_skipped_redundant"] += 1
            if is_helper_request:
                helper_key = (self._today_utc, request_key)
                if helper_key not in self._helper_seen_today:
                    self._helper_seen_today[helper_key] = True
            return copy.deepcopy(self._request_cache[request_key])

        self.metrics["http_requests_cache_misses"] += 1

        last_error: Optional[str] = None
        for attempt in range(1, self.max_request_retries + 1):
            self._check_request_cap()
            self._jitter_sleep()
            self.metrics["http_requests_total"] += 1

            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

                if response.status_code in (429, 503):
                    self._record_rate_limit_event(str(response.status_code), attempt, url)
                    raise requests.HTTPError(f"HTTP {response.status_code}")

                if self._is_challenge_or_login_page(response):
                    self._record_rate_limit_event("challenge_html", attempt, url)
                    raise requests.HTTPError("Challenge/login HTML response received")

                if response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")

                if response.status_code != 200:
                    raise requests.HTTPError(f"HTTP {response.status_code}")

                parsed = response.json()
                self._request_cache[request_key] = parsed
                self._consecutive_rate_limit_events = 0
                if is_helper_request:
                    self._helper_seen_today[(self._today_utc, request_key)] = True
                return copy.deepcopy(parsed)
            except (ValueError, requests.RequestException) as exc:
                last_error = str(exc)
                if attempt >= self.max_request_retries:
                    break
                self.metrics["retry_count_total"] += 1
                self._backoff_sleep(attempt)

        raise RuntimeError(f"Request failed for {url}: {last_error}")

    def fetch_price_data(self, price_guide_url):
        """Fetch price data from TCGPlayer API with run-level cache and safety controls."""
        return self._request_json("GET", price_guide_url)

    def fetch_product_market_price(self, price_url):
        """Fetch market price for a sealed product."""
        try:
            data = self._request_json("GET", price_url)
            first_market_price = data.get("result", [])[0].get("buckets", [])[0].get("marketPrice", None)
            return first_market_price
        except (IndexError, AttributeError, ValueError) as exc:
            print(f"Error parsing data from {price_url}: {exc}")
            return None
        except Exception as exc:
            print(f"Failed to fetch data from {price_url}: {exc}")
            return None

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self.metrics)