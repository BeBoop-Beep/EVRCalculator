import concurrent.futures
import os
import requests


ORIGIN = "http://127.0.0.1:8001"
TOKEN = os.environ["PREMIUM_TEST_TOKEN"]
HEADERS = {"authorization": f"Bearer {TOKEN}"}


def chase(index):
    response = requests.get(
        f"{ORIGIN}/explore/card-chase-efficiency?page={index + 1}&search=q{index}&sort=rank&direction=asc",
        headers=HEADERS, timeout=60,
    )
    return response.status_code, response.headers.get("retry-after"), len(response.content)


def custom(index):
    response = requests.post(
        f"{ORIGIN}/market/explorer/query", headers=HEADERS,
        json={"asset": "cards", "segmentIds": [f"variation-{index}"]}, timeout=60,
    )
    return response.status_code, response.headers.get("retry-after"), len(response.content)


for name, count, runner in [("chase", 20, chase), ("custom", 10, custom)]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        results = list(executor.map(runner, range(count)))
    limited = [result for result in results if result[0] == 429]
    print({
        "probe": name,
        "statuses": {status: sum(1 for result in results if result[0] == status) for status in sorted({result[0] for result in results})},
        "limited": len(limited),
        "allRetryAfterPositive": bool(limited) and all(int(result[1] or "0") > 0 for result in limited),
        "maxLimitedBodyBytes": max((result[2] for result in limited), default=0),
    })
