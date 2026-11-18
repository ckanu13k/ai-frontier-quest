#!/usr/bin/env python3
"""Extend the long-lived Instagram token by another 60 days.

Prints only the new token on stdout (the workflow masks it and saves it as the
IG_ACCESS_TOKEN secret). Meta requires the token to be at least 24 hours old and
unexpired; running weekly keeps it far from its 60-day expiry.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
if not tok:
    sys.exit("IG_ACCESS_TOKEN is not set")
url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "ig_refresh_token", "access_token": tok})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
except urllib.error.HTTPError as e:
    sys.exit(f"refresh failed ({e.code}): {e.read().decode(errors='replace')[:400]}")
new = data.get("access_token")
if not new:
    sys.exit(f"refresh returned no token: {data}")
print(f"::add-mask::{new}")
print(new)
print(f"Token valid for {int(data.get('expires_in', 0)) // 86400} more days.", file=sys.stderr)
