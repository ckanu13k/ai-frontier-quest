#!/usr/bin/env python3
"""Validate AI Frontier Quest content (site/topics.json).

Runs in CI before every deploy and in the weekly content update.
Exits non-zero with a list of problems if the file would break the app.

Usage: python scripts/validate_topics.py [path/to/topics.json]
"""
import datetime as dt
import json
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "site/topics.json"
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOPIC_FIELDS = {
    "id": str, "title": str, "tagline": str, "category": str, "difficulty": int,
    "published": str, "added": str, "lastReviewed": str, "version": int,
    "status": str, "classic": bool, "summary": str, "keyIdeas": list,
    "whyItMatters": str, "numbers": list, "sources": list, "quiz": list, "cards": list,
}


def is_date(s):
    try:
        dt.date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def main():
    errors = []
    err = errors.append
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: cannot parse {PATH}: {e}")
        return 1

    meta = data.get("meta", {})
    cats = meta.get("categories", [])
    for k in ("edition", "generated", "freshnessDays", "categories"):
        if k not in meta:
            err(f"meta.{k} missing")
    if not re.match(r"^\d{4}-W\d{2}$", str(meta.get("edition", ""))):
        err("meta.edition must look like 2026-W47")
    if not is_date(meta.get("generated")):
        err("meta.generated must be an ISO date")
    fd = meta.get("freshnessDays", {})
    if not all(isinstance(fd.get(k), int) for k in ("fresh", "current", "aging")):
        err("meta.freshnessDays needs integer fresh/current/aging")

    log = data.get("changelog", [])
    if not log:
        err("changelog is empty")
    for i, c in enumerate(log):
        if not is_date(c.get("date")) or not c.get("edition") or not isinstance(c.get("items"), list) or not c["items"]:
            err(f"changelog[{i}] needs date, edition and non-empty items")

    topics = data.get("topics", [])
    if not topics:
        err("no topics")
    seen = set()
    active = 0
    for t in topics:
        tid = t.get("id", "?")
        where = f"topic '{tid}'"
        for k, typ in TOPIC_FIELDS.items():
            if k not in t:
                err(f"{where}: missing {k}")
            elif not isinstance(t[k], typ) or (typ is int and isinstance(t[k], bool)):
                err(f"{where}: {k} should be {typ.__name__}")
        if tid in seen:
            err(f"{where}: duplicate id")
        seen.add(tid)
        if not ID_RE.match(str(tid)):
            err(f"{where}: id must be kebab-case")
        if t.get("category") not in cats:
            err(f"{where}: category '{t.get('category')}' not in meta.categories")
        if t.get("difficulty") not in (1, 2, 3):
            err(f"{where}: difficulty must be 1, 2 or 3")
        if t.get("status") not in ("active", "archived"):
            err(f"{where}: status must be active or archived")
        if t.get("status") == "active":
            active += 1
        for k in ("published", "added", "lastReviewed"):
            if not is_date(t.get(k)):
                err(f"{where}: {k} must be an ISO date")
        if not 3 <= len(t.get("keyIdeas", [])) <= 6:
            err(f"{where}: keyIdeas should have 3-6 items")
        for n in t.get("numbers", []):
            if not {"value", "label", "verified"} <= set(n):
                err(f"{where}: each number needs value, label, verified")
        srcs = t.get("sources", [])
        if not srcs:
            err(f"{where}: needs at least one source")
        for s in srcs:
            if not str(s.get("url", "")).startswith("http") or not is_date(s.get("date")):
                err(f"{where}: source needs http(s) url and ISO date")
        quiz = t.get("quiz", [])
        if len(quiz) != 5:
            err(f"{where}: quiz must have exactly 5 questions")
        for qi, q in enumerate(quiz):
            opts = q.get("options", [])
            if len(opts) != 4 or len(set(opts)) != 4:
                err(f"{where}: quiz[{qi}] needs 4 distinct options")
            if not isinstance(q.get("answer"), int) or not 0 <= q.get("answer", -1) < 4:
                err(f"{where}: quiz[{qi}] answer must be 0-3")
            if not q.get("q") or not q.get("explain"):
                err(f"{where}: quiz[{qi}] needs q and explain")
        cards = t.get("cards", [])
        if len(cards) != 5:
            err(f"{where}: cards must have exactly 5 items")
        if any(not c.get("term") or not c.get("def") for c in cards):
            err(f"{where}: every card needs term and def")
        if len({c.get("def") for c in cards}) != len(cards):
            err(f"{where}: card definitions must be distinct")

    if active < 4:
        err(f"only {active} active topics; the arcade needs at least 4")

    if errors:
        print(f"FAIL: {len(errors)} problem(s) in {PATH}")
        for e in errors:
            print(" -", e)
        return 1
    print(f"OK: {PATH} - {len(topics)} topics ({active} active), edition {meta['edition']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
