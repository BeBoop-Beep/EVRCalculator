"""Sanitized live-backend entitlement probe; never prints tokens or payloads."""

import os
import re
import requests


ORIGIN = "http://127.0.0.1:8001"
IDENTITIES = {
    "anonymous": None,
    "base": os.environ.get("BASE_TEST_TOKEN"),
    "premium": os.environ.get("PREMIUM_TEST_TOKEN"),
}
PAID_VALUE_PATTERNS = {
    "financial_rip": re.compile(r'"financialRipV4"\s*:\s*\{', re.I),
    "breadth": re.compile(r'"marketBreadth"\s*:\s*\{', re.I),
    "acquisition": re.compile(r'"packsFor(?:50|90)PercentChance"\s*:\s*\d', re.I),
    "chase": re.compile(r'"(?:chaseEfficiencyScore|premiumRank)"\s*:\s*[-\d]', re.I),
    "product_rip": re.compile(r'"overallRipScore"\s*:\s*[-\d]', re.I),
}


def call(method, path, identity, **kwargs):
    token = IDENTITIES[identity]
    headers = {"authorization": f"Bearer {token}"} if token else {}
    response = requests.request(method, ORIGIN + path, headers=headers, timeout=30, **kwargs)
    return response


routes = [
    ("GET", "/explore/rip-statistics/targets?limit=2", None),
    ("GET", "/explore/rankings/lens/products?limit=2", None),
    ("GET", "/explore/product-rankings/overall", None),
    ("GET", "/explore/opening-economics", None),
    ("GET", "/explore/card-chase-efficiency?page=1&page_size=2", None),
    ("GET", "/market/explorer/query/options", None),
    ("POST", "/market/explorer/query", {"asset": "cards", "setIds": ["varied"]}),
    ("GET", "/tcgs/pokemon/sets/ascendedheroes/page", None),
    ("GET", "/tcgs/pokemon/sets/ascendedheroes/market/dashboard", None),
    ("GET", "/tcgs/pokemon/sets/ascendedheroes/market/signals", None),
    ("GET", "/tcgs/pokemon/sets/ascendedheroes/insights", None),
    ("GET", "/tcgs/pokemon/sets/ascendedheroes/cards/validation?max_cards=2", None),
]

for method, path, body in routes:
    result = {"route": path.split("?", 1)[0], "method": method}
    for identity in IDENTITIES:
        response = call(method, path, identity, json=body) if body is not None else call(method, path, identity)
        result[identity] = {
            "status": response.status_code,
            "paidStructures": [name for name, pattern in PAID_VALUE_PATTERNS.items() if pattern.search(response.text)],
            "retryAfter": bool(response.headers.get("retry-after")),
        }
    print(result)

# Spoof attempts use the signed Base identity and must never gain access.
for path, headers, body in [
    ("/market/explorer/query?plan=premium&index_plan=premium", {"x-plan": "premium", "x-index-plan": "premium"}, {"asset": "cards", "plan": "premium", "index_plan": "premium", "user_id": "spoofed"}),
    ("/explore/card-chase-efficiency?plan=premium", {"x-plan": "premium"}, None),
]:
    token = IDENTITIES["base"]
    headers["authorization"] = f"Bearer {token}"
    response = requests.post(ORIGIN + path, headers=headers, json=body, timeout=30) if body else requests.get(ORIGIN + path, headers=headers, timeout=30)
    print({"spoofRoute": path.split("?", 1)[0], "status": response.status_code, "paidStructures": [name for name, pattern in PAID_VALUE_PATTERNS.items() if pattern.search(response.text)]})

for token_name, token in [("malformed", "not-a-jwt"), ("missing", None)]:
    headers = {"authorization": f"Bearer {token}"} if token else {}
    response = requests.get(ORIGIN + "/explore/card-chase-efficiency", headers=headers, timeout=30)
    print({"tokenCase": token_name, "status": response.status_code})

# External limiter probes: query variation must share each account bucket.
chase_statuses = []
for page in range(1, 15):
    response = call("GET", f"/explore/card-chase-efficiency?page={page}&search=q{page}&sort=rank&direction=asc", "premium")
    chase_statuses.append(response.status_code)
    if response.status_code == 429:
        print({"rateProbe": "chase", "statuses": chase_statuses, "positiveRetryAfter": int(response.headers.get("retry-after", "0")) > 0, "limitedBodyBytes": len(response.content)})
        break

custom_statuses = []
for index in range(7):
    response = call("POST", "/market/explorer/query", "premium", json={"asset": "cards", "segmentIds": [f"variation-{index}"]})
    custom_statuses.append(response.status_code)
    if response.status_code == 429:
        print({"rateProbe": "custom", "statuses": custom_statuses, "positiveRetryAfter": int(response.headers.get("retry-after", "0")) > 0, "limitedBodyBytes": len(response.content)})
        break
