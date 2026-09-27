"""Check the public frontend, its entry asset, API readiness and population catalogue."""

import argparse
import json
import os
import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def origin(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Configure a public HTTPS origin without credentials or a path")
    return value.rstrip("/")


def fetch(url: str, web_origin: str | None = None) -> tuple[bytes, str]:
    headers = {"User-Agent": "Itadb-availability-check", "Cache-Control": "no-cache"}
    if web_origin:
        headers["Origin"] = web_origin
    with urlopen(Request(url, headers=headers), timeout=15) as response:
        if response.status != 200 or response.url != url:
            raise ValueError("Unexpected HTTP status or redirect")
        if web_origin and response.headers.get("Access-Control-Allow-Origin") != web_origin:
            raise ValueError("CORS origin mismatch")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Response exceeds monitoring size limit")
        return body, response.headers.get_content_type()


def check(api_url: str, web_url: str) -> None:
    ready, content_type = fetch(api_url + "/health/ready", web_url)
    if content_type != "application/json" or json.loads(ready) != {"status": "ready"}:
        raise ValueError("API is not ready")
    catalogue, content_type = fetch(api_url + "/v3/populations", web_url)
    payload = json.loads(catalogue)
    if content_type != "application/json" or not isinstance(payload, list) or not payload:
        raise ValueError("Population catalogue is empty or invalid")
    page, content_type = fetch(web_url + "/")
    html = page.decode("utf-8")
    entry = re.search(r'<script\b[^>]*\bsrc="([^"]+)"', html)
    if content_type != "text/html" or 'id="root"' not in html or entry is None:
        raise ValueError("Frontend entry page is invalid")
    asset_url = urljoin(web_url + "/", entry[1])
    if urlsplit(asset_url).netloc != urlsplit(web_url).netloc:
        raise ValueError("Frontend entry asset has an unexpected origin")
    asset, content_type = fetch(asset_url)
    if not asset or content_type not in ("application/javascript", "text/javascript"):
        raise ValueError("Frontend entry asset is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("ITADB_API_URL", ""))
    parser.add_argument("--web-url", default=os.environ.get("ITADB_WEB_URL", ""))
    args = parser.parse_args()
    try:
        api_url, web_url = origin(args.api_url), origin(args.web_url)
    except ValueError as error:
        parser.error(str(error))
    start = time.monotonic()
    for attempt in range(1, 4):
        try:
            check(api_url, web_url)
            print(f"Disponibilità, catalogo, CORS e asset: OK; {time.monotonic() - start:.1f} s")
            return 0
        except (OSError, ValueError) as error:
            # Do not log response bodies, URLs or exception messages from remote servers.
            print(f"Tentativo {attempt}/3 fallito ({type(error).__name__})", flush=True)
            if attempt < 3:
                time.sleep(10)
    print(f"Deployment non disponibile; {time.monotonic() - start:.1f} s")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
