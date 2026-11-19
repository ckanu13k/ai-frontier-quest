#!/usr/bin/env python3
"""Publish whichever queued post is due on Instagram and Threads. Safe to run every few minutes.

- Posts at most one item per run: the earliest post whose time has come.
- A post more than `grace_hours` late is marked missed (and the run fails, so
  GitHub emails you) instead of going out at an odd hour.
- Before publishing it checks the account's latest posts for the same caption,
  so a retry after a half-finished run never double-posts.
- Works with both Meta token types, picked by the token itself:
  system-user tokens from "API setup with Unified login" (start with EAA, never
  expire) go to graph.facebook.com; Instagram Login tokens (start with IG,
  60 days) go to graph.instagram.com. Standard library only.

- Threads (graph.threads.net) gets the same slides as a carousel with a short
  native caption, then replies that form a thread ("In practice", link to the app).
  Instagram and Threads keep separate records, so one never blocks the other.

Env: IG_ACCESS_TOKEN, IG_USER_ID (or config ig_user_id), THREADS_ACCESS_TOKEN,
THREADS_USER_ID (optional), SOCIAL_PAUSED. A platform without a token is skipped.
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

HOST = None  # tests may pin a host; otherwise chosen per token


def host_for(token: str) -> str:
    if HOST:
        return HOST
    return "https://graph.instagram.com" if token.startswith("IG") else "https://graph.facebook.com"


class IG:
    def __init__(self, token: str, version: str, user_id: str | None = None):
        self.token, self.v, self.host = token, version, host_for(token)
        if user_id:
            self.user_id = user_id
        elif "graph.instagram.com" in self.host:
            self.user_id = self.get("me", fields="user_id,username")["user_id"]
        else:
            raise RuntimeError("Set IG_USER_ID (or ig_user_id in config.json): system-user tokens can't look it up")

    def _call(self, method: str, path: str, **params):
        params["access_token"] = self.token
        url = f"{self.host}/{self.v}/{path}"
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


class Threads:
    HOST = "https://graph.threads.net"

    def __init__(self, token: str, version: str, user_id: str | None = None):
        self.token, self.v = token, version
        self.user_id = user_id or self.get("me", fields="id,username")["id"]

    def _call(self, method: str, path: str, **params):
        params["access_token"] = self.token
        url = f"{self.HOST}/{self.v}/{path}"
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
            raise RuntimeError(f"Threads API {method} {path} failed ({e.code}): {body[:600]}") from None

    def get(self, path, **p):
        return self._call("GET", path, **p)

    def post(self, path, **p):
        return self._call("POST", path, **p)

    def wait_ready(self, cid: str, timeout: int = 180):
        t0 = time.time()
        while True:
            r = self.get(cid, fields="status,error_message")
            st = r.get("status")
            if st in ("FINISHED", "PUBLISHED"):
                return
            if st in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Threads container {cid} {st}: {r.get('error_message')}")
            if time.time() - t0 > timeout:
                raise RuntimeError(f"Threads container {cid} not ready after {timeout}s (status {st})")
            time.sleep(5)

    def _publish(self, cid: str) -> str:
        self.wait_ready(cid)
        return self.post(f"{self.user_id}/threads_publish", creation_id=cid)["id"]

    def publish(self, urls: list[str], text: str, topic: str | None) -> str:
        extra = {"topic_tag": topic} if topic else {}
        if len(urls) == 1:
            cid = self.post(f"{self.user_id}/threads", media_type="IMAGE", image_url=urls[0], text=text, **extra)["id"]
        else:
            kids = [self.post(f"{self.user_id}/threads", media_type="IMAGE", image_url=u, is_carousel_item="true")["id"]
                    for u in urls[:10]]
            for k in kids:
                self.wait_ready(k)
            cid = self.post(f"{self.user_id}/threads", media_type="CAROUSEL", children=",".join(kids), text=text, **extra)["id"]
        return self._publish(cid)

    def reply(self, to_id: str, text: str) -> str:
        cid = self.post(f"{self.user_id}/threads", media_type="TEXT", text=text, reply_to_id=to_id)["id"]
        return self._publish(cid)

    def recent(self, n: int = 6) -> list[dict]:
        return self.get(f"{self.user_id}/threads", fields="id,text,permalink,timestamp", limit=n).get("data", [])


def url_ok(u: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30) as r:
            return r.status == 200 and "image/jpeg" in r.headers.get("Content-Type", "")
    except Exception:  # noqa: BLE001
        return False


PLATFORMS = {
    # name: (state key for posted, state key for missed, label)
    "instagram": ("posted", "missed", "Instagram"),
    "threads": ("threads_posted", "threads_missed", "Threads"),
}


def publish_instagram(p: dict, cfg: dict, token: str, uid, now) -> dict:
    ig = IG(token, cfg["graph_api_version"], uid)
    head = p["caption"][:120]
    dup = next((m for m in ig.recent_captions() if (m.get("caption") or "").startswith(head)), None)
    if dup:
        print(f"{p['id']} is already on Instagram ({dup.get('permalink')}); recording it.")
        return {"media_id": dup["id"], "permalink": dup.get("permalink"), "at": dup.get("timestamp")}
    mid = ig.publish(p["urls"], p["caption"])
    link = ig.get(mid, fields="permalink").get("permalink")
    print(f"Published {p['id']} to Instagram ({p['format']}): {link}")
    return {"media_id": mid, "permalink": link, "at": now.isoformat(timespec="minutes")}


def publish_threads(p: dict, cfg: dict, token: str, uid, now, problems: list) -> dict:
    th_post = p.get("threads")
    if not th_post:
        raise RuntimeError("queue has no Threads text for this post (rebuild the week)")
    th = Threads(token, cfg.get("threads_api_version", "v1.0"), uid)
    want = (cfg.get("threads_username") or "").lstrip("@").lower()
    if want:
        got = (th.get("me", fields="username").get("username") or "").lower()
        if got != want:
            raise RuntimeError(f"THREADS_ACCESS_TOKEN belongs to @{got}, not @{want}; refusing to post. Generate a token for @{want}.")
    head = th_post["text"][:100]
    dup = next((m for m in th.recent() if (m.get("text") or "").startswith(head)), None)
    if dup:
        print(f"{p['id']} is already on Threads ({dup.get('permalink')}); recording it.")
        return {"media_id": dup["id"], "permalink": dup.get("permalink"), "at": dup.get("timestamp")}
    mid = th.publish(p["urls"], th_post["text"], th_post.get("topic"))
    rec = {"media_id": mid, "permalink": None, "at": now.isoformat(timespec="minutes"), "replies": []}
    try:
        rec["permalink"] = th.get(mid, fields="permalink").get("permalink")
    except RuntimeError:
        pass
    parent = mid
    for text in th_post.get("replies", []):
        try:  # a failed reply never re-posts the main thread
            parent = th.reply(parent, text)
            rec["replies"].append(parent)
        except RuntimeError as e:
            problems.append(f"{p['id']}: Threads reply failed: {e}")
            break
    print(f"Published {p['id']} to Threads ({p['format']}, {len(rec['replies'])} replies): {rec['permalink']}")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", default=None)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--now", help="pretend UTC time, ISO (testing)")
    ap.add_argument("--post", help="comma-separated post ids to publish now, in this order (e.g. 2026-W47-mon,2026-W47-tue)")
    ap.add_argument("--repost", action="store_true", help="with --post: publish again even if recorded as posted (the duplicate guard still skips posts that are still live)")
    ap.add_argument("--gap", type=int, default=90, help="with --post: seconds to wait between posts")
    a = ap.parse_args()
    cfg = load_json(Path(a.config))
    tokens = {"instagram": os.environ.get("IG_ACCESS_TOKEN", "").strip(),
              "threads": os.environ.get("THREADS_ACCESS_TOKEN", "").strip()}
    uids = {"instagram": os.environ.get("IG_USER_ID", "").strip() or cfg.get("ig_user_id") or None,
            "threads": os.environ.get("THREADS_USER_ID", "").strip() or cfg.get("threads_user_id") or None}

    if a.check:
        ok = False
        if tokens["instagram"]:
            ig = IG(tokens["instagram"], cfg["graph_api_version"], uids["instagram"])
            me = ig.get(ig.user_id, fields="username")
            print(f"Instagram OK: @{me.get('username')} via {ig.host}, user_id {ig.user_id}")
            ok = True
        if tokens["threads"]:
            th = Threads(tokens["threads"], cfg.get("threads_api_version", "v1.0"), uids["threads"])
            me = th.get("me", fields="id,username")
            lim = th.get(f"{th.user_id}/threads_publishing_limit", fields="quota_usage,config")
            print(f"Threads OK: @{me.get('username')}, user_id {th.user_id}; quota: {json.dumps(lim.get('data'))}")
            ok = True
        if not ok:
            print("No IG_ACCESS_TOKEN or THREADS_ACCESS_TOKEN set.")
        return 0 if ok else 1

    if cfg.get("paused") or os.environ.get("SOCIAL_PAUSED", "").lower() in ("1", "true", "yes"):
        print("Paused (config.json 'paused' or SOCIAL_PAUSED). Nothing posted.")
        return 0
    active = [name for name in PLATFORMS if tokens[name] or a.dry_run]
    if not active:
        print("No platform connected yet (no IG_ACCESS_TOKEN or THREADS_ACCESS_TOKEN). Nothing posted.")
        return 0
    assets = Path(a.assets)
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=dt.timezone.utc) if a.now else dt.datetime.now(dt.timezone.utc)
    state = load_json(assets / "state.json", {"posted": {}, "missed": {}, "featured": {}})
    queues = [load_json(q) for q in sorted((assets / "queue").glob("*.json"))]
    grace = dt.timedelta(hours=cfg["grace_hours"])
    problems, changed = [], False
    connected = state.setdefault("connected", {})

    if a.post:
        ids = [x.strip() for x in a.post.split(",") if x.strip()]
        by_id = {p["id"]: p for q in queues for p in q["posts"]}
        unknown = [x for x in ids if x not in by_id]
        if unknown:
            print(f"::error::Not in the queue: {', '.join(unknown)}")
            return 1
        for i, pid in enumerate(ids):
            p = by_id[pid]
            if not all(url_ok(u) for u in p["urls"]):
                problems.append(f"{pid}: images not live at {p['urls'][0]}")
                continue
            for name in active:
                posted_key, missed_key, label = PLATFORMS[name]
                posted, missed = state.setdefault(posted_key, {}), state.setdefault(missed_key, {})
                if pid in posted and not a.repost:
                    print(f"{label}: {pid} already posted ({posted[pid].get('permalink')}); skipping.")
                    continue
                if a.dry_run or not tokens[name]:
                    print(f"[dry run] {label}: would publish {pid} now ({p['format']}).")
                    continue
                try:
                    rec = (publish_instagram(p, cfg, tokens[name], uids[name], now) if name == "instagram"
                           else publish_threads(p, cfg, tokens[name], uids[name], now, problems))
                    if pid in posted and rec.get("media_id") == posted[pid].get("media_id"):
                        print(f"{label}: {pid} is still live, so it was not posted again. Delete it first to repost.")
                    posted[pid] = rec
                    missed.pop(pid, None)
                except RuntimeError as e:
                    problems.append(f"{label}: {pid}: {e}")
                changed = True
            if i < len(ids) - 1 and not a.dry_run:
                time.sleep(a.gap)  # keep the posts in order and a little apart
        active = []  # manual run: skip the scheduled pass

    for name in active:
        posted_key, missed_key, label = PLATFORMS[name]
        posted, missed = state.setdefault(posted_key, {}), state.setdefault(missed_key, {})
        if tokens[name] and name not in connected:
            connected[name] = now.isoformat(timespec="minutes")
            changed = True
        since = dt.datetime.fromisoformat(connected[name]) if name in connected else now
        due = []
        for q in queues:
            built = dt.datetime.fromisoformat(q["built"])
            for p in q["posts"]:
                if p["id"] in posted or p["id"] in missed:
                    continue
                when = dt.datetime.fromisoformat(p["scheduled_at"])
                if when > now:
                    continue
                if when < max(built, since) - grace:
                    # slot passed before the queue was built or before this platform was connected
                    missed[p["id"]] = {"at": now.isoformat(timespec="minutes"), "reason": "slot passed before build or connection"}
                    changed = True
                elif now - when > grace:
                    missed[p["id"]] = {"at": now.isoformat(timespec="minutes"), "reason": "not published within grace window"}
                    problems.append(f"{label}: {p['id']} missed its slot ({p['scheduled_local']})")
                    changed = True
                else:
                    due.append(p)
        if not due:
            nxt = min((p for q in queues for p in q["posts"] if p["id"] not in posted and p["id"] not in missed
                       and dt.datetime.fromisoformat(p["scheduled_at"]) > now), key=lambda p: p["scheduled_at"], default=None)
            print(f"{label}: nothing due." + (f" Next: {nxt['id']} at {nxt['scheduled_local']}." if nxt else " Queue is empty."))
            continue
        p = min(due, key=lambda p: p["scheduled_at"])
        if not all(url_ok(u) for u in p["urls"]):
            print(f"{label}: {p['id']} images not live yet at {p['urls'][0]}; will retry next run.")
            continue
        if a.dry_run or not tokens[name]:
            extra = f" with {len(p.get('threads', {}).get('replies', []))} replies" if name == "threads" else ""
            print(f"[dry run] {label}: would publish {p['id']} ({p['format']}, {len(p['urls'])} slides{extra}).")
            continue
        try:
            if name == "instagram":
                posted[p["id"]] = publish_instagram(p, cfg, tokens[name], uids[name], now)
            else:
                posted[p["id"]] = publish_threads(p, cfg, tokens[name], uids[name], now, problems)
        except RuntimeError as e:
            problems.append(f"{label}: {p['id']}: {e}")
        changed = True

    if changed:
        save_json(assets / "state.json", state)
        (assets / "index.html").write_text(preview_html(list(reversed(queues)), state), encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
    for m in problems:
        print(f"::error::{m}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
