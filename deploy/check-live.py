#!/usr/bin/env python3
"""Verify the deployed receipt, pages, assets, contact data, and audio seeking."""
import json
import re
import sys
import urllib.error
import urllib.request


def check(base, expected_commit):
    base = base.rstrip("/")

    def request(path, headers=None):
        return urllib.request.urlopen(urllib.request.Request(base + path, headers=headers or {}), timeout=20)

    with request("/release.json") as response:
        receipt = json.loads(response.read(65536))
        if receipt["commit"] != expected_commit:
            raise ValueError("Live release does not match the deployment commit")
    for path in ("/", "/projects/mb4x-radio-archive/", "/projects/expeditionops/"):
        with request(path) as response:
            if response.status != 200 or "text/html" not in response.headers.get("Content-Type", ""):
                raise ValueError(f"Page failed: {path}")
            html = response.read(1024 * 1024).decode()
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
                with request(asset) as asset_response:
                    if asset_response.status != 200:
                        raise ValueError(f"Asset failed: {asset}")
    with request("/data/contacts.json") as response:
        if len(json.loads(response.read(16 * 1024 * 1024))["contacts"]) != 4606:
            raise ValueError("Contact index is incomplete")
    for number in range(1, 9):
        with request(f"/audio/recording-{number:02}.mp3", {"Range": "bytes=0-15"}) as response:
            if response.status != 206 or len(response.read(17)) != 16:
                raise ValueError(f"Audio range failed: recording {number}")
    print(f"Verified live deployment {expected_commit} at {base}")


if __name__ == "__main__":
    try:
        check(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as error:
        print(f"Live check failed: {error}", file=sys.stderr)
        sys.exit(1)
