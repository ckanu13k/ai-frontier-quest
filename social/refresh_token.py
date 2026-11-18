#!/usr/bin/env python3
"""Extend a 60-day Meta token (Instagram Login or Threads) by another 60 days.

Usage: python social/refresh_token.py instagram|threads
Reads IG_ACCESS_TOKEN or THREADS_ACCESS_TOKEN. Prints a GitHub mask line, then
only the new token on stdout (the workflow saves it back as the same secret).
Meta requires the token to be at least 24 hours old and unexpired; running
weekly keeps it far from expiry.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PLATFORMS = {
    "instagram": ("IG_ACCESS_TOKEN", "https://graph.instagram.com/refresh_access_token", "ig_refresh_token"),
    "threads": ("THREADS_ACCESS_TOKEN", "https://graph.threads.net/refresh_access_token", "th_refresh_token"),
}
name = sys.argv[1] if len(sys.argv) > 1 else "instagram"
env, endpoint, grant = PLATFORMS[name]
tok = os.environ.get(env, "").strip()
if not tok:
    sys.exit(f"{env} is not set")
url = endpoint + "?" + urllib.parse.urlencode({"grant_type": grant, "access_token": tok})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
except urllib.error.HTTPError as e:
    sys.exit(f"{name} refresh failed ({e.code}): {e.read().decode(errors='replace')[:400]}")
new = data.get("access_token")
if not new:
    sys.exit(f"{name} refresh returned no token: {data}")
print(f"::add-mask::{new}")
print(new)
print(f"{name} token valid for {int(data.get('expires_in', 0)) // 86400} more days.", file=sys.stderr)
