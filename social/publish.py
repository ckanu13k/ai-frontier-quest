#!/usr/bin/env python3
"""Publish whichever queued Instagram post is due. Safe to run every few minutes.

- Posts at most one item per run: the earliest post whose time has come.
- A post more than `grace_hours` late is marked missed (and the run fails, so
  GitHub emails you) instead of going out at an odd hour.
- Before publishing it checks the account's latest posts for the same caption,
  so a retry after a half-finished run never double-posts.
- Uses the Instagram API with Instagram Login (graph.instagram.com). Standard
  library only.

Env: IG_ACCESS_TOKEN (required to post), IG_USER_ID (optional), SOCIAL_PAUSED.
Usage:
  python social/publish.py --assets ../assets            # normal run
  python social/publish.py --assets ../assets --dry-run  # say what would happen
  python social/publish.py --check                       # verify token + account
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_week import load_json, preview_html, save_json  # noqa: E402

HOST = "https://graph.instagram.com"


class IG:
    def __init__(self, token: str, version: str, user_id: str | None = None):
        self.token, self.v = token, version
        self.user_id = user_id or self.get("me", fields="user_id,username")["user_id"]

    def _call(self, method: str, path: str, **params):
        params["access_token"] = self.token
        url = f"{HOST}/{self.v}/{path}"
        data = None
        if method == "GET":
            url += "?" + urllib.parse.urlencode(params)
        else:
            data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"Instagram API {method} {path} failed ({e.code}): {body[:600]}") from None

    def get(self, path, **p):
        return self._call("GET", path, **p)

    def post(self, path, **p):
        return self._call("POST", path, **p)

    def wait_ready(self, container_id: str, timeout: int = 120):
        t0 = time.time()
        while True:
            st = self.get(container_id, fields="status_code").get("status_code")
            if st in ("FINISHED", "PUBLISHED"):
                return
            if st in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"container {container_id} status {st}")
            if time.time() - t0 > timeout:
                raise RuntimeError(f"container {container_id} not ready after {timeout}s (status {st})")
            time.sleep(4)

    def publish(self, urls: list[str], caption: str) -> str:
        if len(urls) == 1:
            cid = self.post(f"{self.user_id}/media", image_url=urls[0], caption=caption)["id"]
        else:
            kids = []
            for u in urls[:10]:  # carousel limit
                kids.append(self.post(f"{self.user_id}/media", image_url=u, is_carousel_item="true")["id"])
            for k in kids:
                self.wait_ready(k)
            cid = self.post(f"{self.user_id}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
        self.wait_ready(cid)
        return self.post(f"{self.user_id}/media_publish", creation_id=cid)["id"]

    def recent_captions(self, n: int = 6) -> list[dict]:
        return self.get(f"{self.user_id}/media", fields="id,caption,permalink,timestamp", limit=n).get("data", [])


def url_ok(u: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30) as r:
            return r.status == 200 and "image/jpeg" in r.headers.get("Content-Type", "")
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", default=None)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--now", help="pretend UTC time, ISO (testing)")
    a = ap.parse_args()
    cfg = load_json(Path(a.config))
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()

    if a.check:
        if not token:
            print("IG_ACCESS_TOKEN is not set."); return 1
        ig = IG(token, cfg["graph_api_version"], os.environ.get("IG_USER_ID") or None)
        me = ig.get("me", fields="user_id,username,account_type")
        lim = ig.get(f"{ig.user_id}/content_publishing_limit", fields="quota_usage,config")
        print(f"OK: @{me.get('username')} ({me.get('account_type')}), user_id {ig.user_id}; publishing quota: {json.dumps(lim.get('data'))}")
        return 0

    if cfg.get("paused") or os.environ.get("SOCIAL_PAUSED", "").lower() in ("1", "true", "yes"):
        print("Paused (config.json 'paused' or SOCIAL_PAUSED). Nothing posted.")
        return 0
    if not token and not a.dry_run:
        print("Instagram is not connected yet (no IG_ACCESS_TOKEN secret). Nothing posted.")
        return 0
    assets = Path(a.assets)
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=dt.timezone.utc) if a.now else dt.datetime.now(dt.timezone.utc)
    state = load_json(assets / "state.json", {"posted": {}, "missed": {}, "featured": {}})
    queues = [load_json(p) for p in sorted((assets / "queue").glob("*.json"))]
    grace = dt.timedelta(hours=cfg["grace_hours"])
    due, problems, changed = [], [], False

    for q in queues:
        built = dt.datetime.fromisoformat(q["built"])
        for p in q["posts"]:
            if p["id"] in state["posted"] or p["id"] in state["missed"]:
                continue
            when = dt.datetime.fromisoformat(p["scheduled_at"])
            if when > now:
                continue
            if when < built - grace:
                # slot had already passed when this queue was built (e.g. a mid-week first run)
                state["missed"][p["id"]] = {"at": now.isoformat(timespec="minutes"), "reason": "slot passed before build"}
                changed = True
                continue
            if now - when > grace:
                state["missed"][p["id"]] = {"at": now.isoformat(timespec="minutes"), "reason": "not published within grace window"}
                problems.append(f"{p['id']} missed its slot ({p['scheduled_local']})")
                changed = True
            else:
                due.append(p)

    due.sort(key=lambda p: p["scheduled_at"])
    nxt = min((p for q in queues for p in q["posts"] if p["id"] not in state["posted"] and p["id"] not in state["missed"]
               and dt.datetime.fromisoformat(p["scheduled_at"]) > now), key=lambda p: p["scheduled_at"], default=None)

    if due:
        p = due[0]
        if not all(url_ok(u) for u in p["urls"]):
            msg = f"{p['id']}: images not live yet at {p['urls'][0]}; will retry next run."
            print(msg)
        elif a.dry_run or not token:
            print(f"[dry run] would publish {p['id']} ({p['format']}, {len(p['urls'])} slides). "
                  + ("" if token else "IG_ACCESS_TOKEN not set."))
        else:
            ig = IG(token, cfg["graph_api_version"], os.environ.get("IG_USER_ID") or None)
            head = p["caption"][:120]
            dup = next((m for m in ig.recent_captions() if (m.get("caption") or "").startswith(head)), None)
            if dup:
                print(f"{p['id']} is already on Instagram ({dup.get('permalink')}); recording it.")
                state["posted"][p["id"]] = {"media_id": dup["id"], "permalink": dup.get("permalink"), "at": dup.get("timestamp")}
            else:
                try:
                    mid = ig.publish(p["urls"], p["caption"])
                    link = ig.get(mid, fields="permalink").get("permalink")
                    state["posted"][p["id"]] = {"media_id": mid, "permalink": link, "at": now.isoformat(timespec="minutes")}
                    print(f"Published {p['id']} ({p['format']}): {link}")
                except RuntimeError as e:
                    problems.append(f"{p['id']}: {e}")
            changed = True
    else:
        print("Nothing due." + (f" Next: {nxt['id']} at {nxt['scheduled_local']}." if nxt else " Queue is empty."))

    if changed:
        save_json(assets / "state.json", state)
        keep = [q for q in reversed(queues)]
        (assets / "index.html").write_text(preview_html(keep, state), encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
    for m in problems:
        print(f"::error::{m}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
