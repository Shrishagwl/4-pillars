"""Verify a private Cloud Run release. Read tokens from the environment, never argv."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an authentication token to a redirect destination.
        return None


def check_health(url, service, version, token, *, opener=None):
    if not re.fullmatch(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app", url):
        raise ValueError("Health destination must be a Cloud Run HTTPS base URL")
    if not token or not service or not version:
        raise ValueError("ID token, expected service and expected release are required")
    request = Request(url + "/health", headers={
        "X-Serverless-Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    opener = opener or build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"Health check failed for {service}: HTTP {response.status}")
            payload = json.loads(response.read(4097))
    except HTTPError as error:
        raise RuntimeError(f"Health check failed for {service}: HTTP {error.code}") from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError(f"Health response unavailable or invalid for {service}") from None
    if not isinstance(payload, dict) or any(payload.get(key) != expected for key, expected in {
        "status": "ok", "service": service, "version": version,
    }.items()):
        raise RuntimeError(f"Health identity or release mismatch for {service}")
    return payload


def main():
    service = os.environ["EXPECTED_SERVICE"]
    version = os.environ["EXPECTED_VERSION"]
    check_health(os.environ["CLOUD_RUN_URL"], service, version,
                 os.environ["CLOUD_RUN_ID_TOKEN"])
    print(f"Verified private health: {service} at release {version}")


if __name__ == "__main__":
    main()
