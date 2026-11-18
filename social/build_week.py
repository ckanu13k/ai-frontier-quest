#!/usr/bin/env python3
"""Turn the week's AI Frontier Quest content into 7 scheduled Instagram carousels.

Reads site/topics.json (the same file the weekly Claude refresh writes), picks the
week's topics, writes captions, renders slides, and saves a queue the publisher
reads. Everything it says comes from topics.json; nothing new is invented here.

Usage:
  python social/build_week.py --assets ../assets            # build this week if needed
  python social/build_week.py --assets ../assets --force    # rebuild anyway
  python social/build_week.py --assets /tmp/preview --week 2026-W47 --now 2026-11-16T05:00
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DIFF = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
DATE_LIKE = re.compile(r"\b(19|20)\d{2}\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)


# ---------- helpers ----------

def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def nice(s: str) -> str:
    x = d(s)
    return f"{x.strftime('%b')} {x.day}, {x.year}"


def short(s: str) -> str:
    x = d(s)
    return f"{x.strftime('%b')} {x.day}"


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def short_title(t: dict) -> str:
    return t["title"].split(":")[0].strip()


def week_key(day: dt.date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def week_monday(key: str) -> dt.date:
    y, w = key.split("-W")
    return dt.date.fromisocalendar(int(y), int(w), 1)


def jitter(post_id: str, spread: int) -> int:
    if spread <= 0:
        return 0
    h = int(hashlib.sha256(post_id.encode()).hexdigest(), 16)
    return h % (2 * spread + 1) - spread


def freshness(t: dict, today: dt.date, fd: dict) -> dict:
    if t.get("classic"):
        return {"text": "Classic", "tone": "violet"}
    age = (today - d(t["published"])).days
    label = "Fresh" if age <= fd.get("fresh", 30) else "Current" if age <= fd.get("current", 120) else "Aging"
    return {"text": f"{label} · {short(t['published'])}", "tone": "" if label == "Fresh" else "amber"}


def stat_ok(n: dict) -> bool:
    return not DATE_LIKE.search(n["value"]) and len(n["value"]) <= 16


def stat_score(n: dict) -> int:
    """Rank figures for a numbers post: verified, unit-bearing and non-trivial values first."""
    v = n["value"]
    score = 3 if n.get("verified", True) else 0
    if re.search(r"%|\d\s*x\b|[KMB]\+?$|[KMB]\b|GB|TB|tok|/s|/kg|\$|\bh\b|hours?|days?|weeks?|months?", v):
        score += 2
    if re.fullmatch(r"~?\d{1,2}", v.strip()):
        score -= 3  # bare small counts ("0", "3") rarely stop a scroll
    return score


def hashtags(cfg: dict, topics: list[dict]) -> str:
    tags = list(cfg["base_hashtags"][:2])
    for t in topics:
        tag = cfg["category_hashtags"].get(t["category"])
        if tag and tag not in tags:
            tags.append(tag)
    tags = tags[:4] + [cfg["brand_hashtag"]]  # Instagram now caps posts at 5 hashtags
    return " ".join(tags)


THREADS_LIMIT = 500  # Threads counts UTF-8 bytes, so emoji cost more than one character


def nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


def fit(text: str, limit: int = THREADS_LIMIT) -> str:
    if nbytes(text) <= limit:
        return text
    while nbytes(text + "…") > limit:
        text = text[: text.rstrip().rfind(" ")] if " " in text.strip() else text[:-1]
    return text.rstrip(" ,;:") + "…"


def fit_lines(intro: str, lines: list[str], outro: str, more: str = "…and more in the slides.") -> str:
    """Intro, as many whole lines as fit, then outro, all within the Threads limit."""
    kept = []
    for ln in lines:
        trial = "\n\n".join([intro, "\n".join(kept + [ln]), more, outro])
        if nbytes(trial) > THREADS_LIMIT:
            break
        kept.append(ln)
    if not kept:
        return fit(f"{intro}\n\n{outro}")
    body = "\n".join(kept) + ("" if len(kept) == len(lines) else "\n" + more)
    return fit("\n\n".join([intro, body, outro]))


def threads_post(cfg: dict, topics: list[dict], text: str, replies: list[str]) -> dict:
    tags = cfg.get("threads_topics", {})
    topic = tags.get(topics[0]["category"], tags.get("default")) if topics else tags.get("default")
    return {"text": fit(text), "replies": [fit(r) for r in replies if r], "topic": topic}


def caption(*parts: str) -> str:
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    return text[:2190]


# ---------- topic selection ----------

def pick_topics(data: dict, state: dict, monday: dt.date, cfg: dict):
    active = [t for t in data["topics"] if t.get("status") == "active"]
    since = monday - dt.timedelta(days=7)

    def is_fresh(t):
        return d(t["added"]) >= since or (t.get("version", 1) > 1 and d(t["lastReviewed"]) >= since)

    fresh = sorted([t for t in active if is_fresh(t) and not t.get("classic")], key=lambda t: t["published"], reverse=True)
    hist = state.setdefault("featured", {})
    cooldown = cfg["deep_dive_cooldown_weeks"]

    def cooled(t):
        h = hist.get(t["id"])
        if not h:
            return True
        if t.get("version", 1) > h.get("version", 1):
            return True  # materially refreshed since we last covered it
        weeks = (monday - week_monday(h["week"])).days // 7
        return weeks >= cooldown

    picks = [t for t in fresh if cooled(t)][:3]
    if len(picks) < 3:
        rest = [t for t in active if t not in picks and cooled(t)]
        # never-featured first, then longest since featured; within those, newest content first
        rest.sort(key=lambda t: (hist.get(t["id"], {}).get("week", "0000"), -d(t["published"]).toordinal()))
        picks += rest[: 3 - len(picks)]
    return fresh, picks


# ---------- post formats ----------

def deep_dive(t: dict, cfg: dict, today: dt.date, fd: dict, vault: bool) -> tuple[list, str]:
    cat, classic = t["category"], t.get("classic", False)
    base = {"category": cat, "classic": classic}
    kicker = ("From the vault" if vault else "Deep dive") + f" · {DIFF.get(t['difficulty'], '')}"
    slides = [{**base, "kind": "cover", "kicker": kicker, "title": t["title"], "sub": t["tagline"],
               "pills": [freshness(t, today, fd), {"text": f"{len(t['keyIdeas'][:4])} key ideas"}]},
              {**base, "kind": "text", "kicker": "What happened", "text": t["summary"]}]
    for i, idea in enumerate(t["keyIdeas"][:4], 1):
        slides.append({**base, "kind": "idea", "n": f"{i:02d}", "text": idea})
    nums = [n for n in t["numbers"] if stat_ok(n)]
    nums.sort(key=lambda n: not n.get("verified", True))
    if nums:
        slides.append({**base, "kind": "numbers", "items": nums[:4]})
    slides.append({**base, "kind": "text", "kicker": "Why it matters", "tone": "amber", "text": t["whyItMatters"]})
    if t.get("inPractice"):
        slides.append({**base, "kind": "practice", "kicker": "In practice", "text": t["inPractice"]})
    terms = ", ".join(c["term"] for c in t["cards"][:3])
    srcs = [f"{s['publisher']}: {s['title']} ({short(s['date'])})" for s in t["sources"][:3]]
    slides.append({**base, "kind": "cta", "heading": "Master it in 5 minutes",
                   "bullets": [f"5-question quiz on {short_title(t)}", f"Recall cards: {terms}", "A timed term match to lock it in"],
                   "sources": srcs})
    reported = any(not n.get("verified", True) for n in nums[:4])
    pubs = ", ".join(dict.fromkeys(s["publisher"] for s in t["sources"]))
    cap = caption(
        f"{t['title']} 👇",
        t["tagline"] + " " + first_sentence(t["whyItMatters"]),
        f"💡 In practice: {t['inPractice']}" if t.get("inPractice") else "",
        f"Inside: what happened, {len(t['keyIdeas'][:4])} key ideas{', the numbers' if nums else ''}, why it matters"
        f"{' and how it is used' if t.get('inPractice') else ''}. Swipe →",
        "📌 Save this for later.\n🎮 Take the 5-question quiz on it in AI Frontier Quest. Link in bio.",
        f"Sources: {pubs}." + ("\nFigures tagged REPORTED come from press coverage and are not independently verified." if reported else ""),
        hashtags(cfg, [t]),
    )
    th = threads_post(cfg, [t], f"{t['title']}\n\n{t['tagline']} {first_sentence(t['whyItMatters'])}\n\nSwipe for the key ideas and numbers 👇", [
        f"💡 In practice: {t['inPractice']}" if t.get("inPractice") else "",
        f"Learn it in 5 minutes, then take the quiz: {cfg['app_url']}\n\nSources: {pubs}."
        + (" Figures tagged REPORTED come from press coverage." if reported else ""),
    ])
    return slides, cap, th


def weekly_brief(topics: list[dict], cfg: dict, today: dt.date, fd: dict, monday: dt.date, fresh: bool) -> tuple[list, str]:
    sunday = monday + dt.timedelta(days=6)
    rng = (f"{short(monday.isoformat())}–{sunday.day}" if monday.month == sunday.month
           else f"{short(monday.isoformat())}–{short(sunday.isoformat())}")
    n = len(topics)
    title = "New on the AI frontier" if fresh else "Catch up on the AI frontier"
    slides = [{"kind": "cover", "kicker": f"Weekly brief · {rng}", "title": title,
               "sub": f"{n} developments worth knowing, in under a minute.", "pills": [{"text": "Synthesized from primary sources"}]}]
    for i, t in enumerate(topics, 1):
        slides.append({"kind": "brief_item", "category": t["category"], "classic": t.get("classic", False),
                       "n": f"{i:02d} / {n:02d}", "title": t["title"], "tagline": t["tagline"],
                       "pills": [freshness(t, today, fd)]})
    slides.append({"kind": "cta", "heading": "Learn them all this week", "bullets": [
        "5-minute briefings built from lab blogs and papers", "Quizzes, recall cards and a timed term match",
        "A Boss Battle every week and new topics every Monday"]})
    lines = "\n".join(f"{i}. {short_title(t)}: {t['tagline']}" for i, t in enumerate(topics, 1))
    cap = caption(
        f"{n} new developments on the AI frontier 👇" if fresh else f"{n} AI developments worth catching up on 👇",
        lines,
        "Which one matters most for your work? Tell us in the comments.",
        "Learn each in 5 minutes, then test yourself in the weekly Boss Battle. AI Frontier Quest, link in bio.",
        hashtags(cfg, topics),
    )
    intro = f"{n} new developments on the AI frontier this week 🧵" if fresh else f"{n} AI developments worth catching up on 🧵"
    th = threads_post(cfg, topics, fit_lines(intro, [f"{i}. {short_title(t)}: {t['tagline']}" for i, t in enumerate(topics, 1)],
                                             "Which one matters most for your work?"),
                      [f"Learn each in 5 minutes, then try this week's Boss Battle: {cfg['app_url']}"])
    th["topic"] = cfg.get("threads_topics", {}).get("default")
    return slides, cap, th


def quiz(topics: list[dict], cfg: dict, monday: dt.date) -> tuple[list, str] | None:
    qs = []
    wk = monday.isocalendar()[1]
    for i, t in enumerate(topics):
        pool = sorted(range(len(t["quiz"])), key=lambda j: len(t["quiz"][j]["q"]) + sum(map(len, t["quiz"][j]["options"])))
        ok = [j for j in pool if len(t["quiz"][j]["q"]) + sum(map(len, t["quiz"][j]["options"])) <= 330] or pool[:1]
        qs.append((t, t["quiz"][ok[(wk + i) % len(ok)]]))
    if not qs:
        return None
    n = len(qs)
    slides = [{"kind": "cover", "kicker": "Weekly challenge", "title": f"{n} questions. No Googling.",
               "sub": "Comment your answers first, then swipe for the solutions.", "pills": [{"text": "Based on this week's research", "tone": "amber"}]}]
    for i, (t, q) in enumerate(qs, 1):
        base = {"category": t["category"], "classic": t.get("classic", False), "question": q["q"], "options": q["options"]}
        slides.append({**base, "kind": "quiz_q", "kicker": f"Question {i} of {n}"})
        slides.append({**base, "kind": "quiz_a", "kicker": f"Answer {i}: {'ABCD'[q['answer']]}", "answer": q["answer"], "explain": q["explain"]})
    slides.append({"kind": "cta", "heading": f"Got {n}/{n}? Try the Boss Battle", "bullets": [
        "Harder questions on every topic this week", "A 60-second Blitz and a Daily Challenge", "XP, streaks and badges as you learn"]})
    about = "; ".join(f"Q{i}: {short_title(t)}" for i, (t, _) in enumerate(qs, 1))
    cap = caption(
        f"Quiz time: {n} questions on this week's AI research 🧠",
        "Drop your answers in the comments (like 1B 2D 3A) before you swipe to the solutions.",
        about + ".",
        "Want more? The full Boss Battle is in AI Frontier Quest. Link in bio.",
        hashtags(cfg, [t for t, _ in qs]),
    )
    th = threads_post(cfg, [], f"Quiz time: {n} questions on this week's AI research 🧠\n\nReply with your answers (like 1B 2D 3A), then swipe for the solutions.\n\n{about}.",
                      [f"Got {n}/{n}? The full Boss Battle is waiting: {cfg['app_url']}"])
    return slides, cap, th


def by_the_numbers(topics: list[dict], cfg: dict) -> tuple[list, str] | None:
    cands = [(t, n) for t in topics for n in t["numbers"] if stat_ok(n)]
    cands.sort(key=lambda tn: -stat_score(tn[1]))  # stable: keeps topic order within a score
    picked = []
    for t, n in cands:
        if stat_score(n) > 0 and sum(1 for x, _ in picked if x is t) < 2:
            picked.append((t, n))
    picked = picked[:5]
    if len(picked) < 3:
        return None
    k = len(picked)
    slides = [{"kind": "cover", "kicker": "By the numbers", "title": f"The week in AI, in {k} numbers",
               "sub": "Every figure comes from the original announcement or paper.", "pills": [{"text": "Swipe for the context", "tone": "amber"}]}]
    for t, n in picked:
        slides.append({"kind": "stat", "category": t["category"], "classic": t.get("classic", False), "kicker": short_title(t),
                       "value": n["value"], "label": n["label"], "verified": n.get("verified", True), "from": t["tagline"]})
    slides.append({"kind": "cta", "heading": "Know what's behind each number", "bullets": [
        "Short briefings with every source linked", "Quizzes that check you really got it", "New topics every Monday"]})
    if any(not n.get("verified", True) for _, n in picked):
        slides[0]["sub"] = "Figures marked REPORTED come from press coverage, not the primary source."
    lines = "\n".join(f"• {n['value']}: {n['label']} ({short_title(t)})" for t, n in picked)
    cap = caption(
        f"The week in AI, in {k} numbers 📊",
        lines,
        "Which one surprised you most?",
        "Get the full story behind each in AI Frontier Quest. Link in bio.",
        hashtags(cfg, [t for t, _ in picked]),
    )
    rep = any(not n.get("verified", True) for _, n in picked)
    th = threads_post(cfg, [], fit_lines(f"The week in AI, in {k} numbers 📊", [f"• {n['value']}: {n['label']}" for _, n in picked],
                                         "Which one surprised you most?"),
                      [f"The story behind each number, with sources: {cfg['app_url']}"
                       + ("\n\nFigures tagged REPORTED come from press coverage." if rep else "")])
    return slides, cap, th


def terms(topics: list[dict], cfg: dict) -> tuple[list, str] | None:
    picked = []
    for t in topics:
        cards = sorted(t["cards"], key=lambda c: len(c["def"]))
        picked += [(t, c) for c in cards[:2]]
    picked = picked[:6]
    if len(picked) < 3:
        return None
    k = len(picked)
    slides = [{"kind": "cover", "kicker": "Glossary", "title": f"{k} AI terms you'll hear this week",
               "sub": "Plain-English definitions. Save this for your next meeting.", "pills": [{"text": "Swipe to learn"}]}]
    for t, c in picked:
        slides.append({"kind": "term", "category": t["category"], "classic": t.get("classic", False),
                       "term": c["term"], "definition": c["def"], "from": short_title(t)})
    slides.append({"kind": "cta", "heading": "Make them stick", "bullets": [
        "Spaced-repetition Review deck", "Timed term match", "New terms every week"]})
    lines = "\n".join(f"• {c['term']}: {c['def']}" for _, c in picked)
    cap = caption(
        f"{k} AI terms you'll hear this week, in plain English 📚",
        lines,
        "📌 Save this so it's there when you need it.",
        "Drill them with spaced repetition in AI Frontier Quest. Link in bio.",
        hashtags(cfg, [t for t, _ in picked]),
    )
    th = threads_post(cfg, [], fit_lines(f"{k} AI terms you'll hear this week, in plain English 📚",
                                         [f"• {c['term']}: {c['def']}" for _, c in picked], "Save this for your next meeting."),
                      [f"Drill them with spaced repetition: {cfg['app_url']}"])
    return slides, cap, th


# ---------- preview page ----------

def preview_html(queues: list[dict], state: dict) -> str:
    esc = html.escape
    out = ["<!doctype html><html><head><meta charset='utf-8'><meta name='robots' content='noindex'>",
           "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Instagram queue · AI Frontier Quest</title>",
           "<style>body{font-family:system-ui,sans-serif;background:#0B1120;color:#E5E9F0;margin:0;padding:24px}h1{font-size:22px}"
           "h2{font-size:18px;margin:36px 0 8px}.post{background:#111A2B;border:1px solid #233049;border-radius:16px;padding:16px;margin:14px 0}"
           ".row{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px}.row img{height:300px;border-radius:8px}"
           "pre{white-space:pre-wrap;font:14px/1.5 system-ui;color:#C9D2DF}.st{font:600 12px monospace;padding:3px 8px;border-radius:6px;background:#233049}"
           ".ok{background:#14532d}.miss{background:#7f1d1d}</style></head><body><h1>Instagram queue</h1>"]
    for q in queues:
        out.append(f"<h2>{esc(q['week'])} · built {esc(q['built'])} from edition {esc(q['edition'])}</h2>")
        for p in q["posts"]:
            badges = []
            for label, pk, mk in (("Instagram", "posted", "missed"), ("Threads", "threads_posted", "threads_missed")):
                st = state.get(pk, {}).get(p["id"])
                ms = state.get(mk, {}).get(p["id"])
                badges.append(f"<span class='st ok'>{label}: posted</span> <a href='{esc(st.get('permalink') or '')}' style='color:#5EEAD4'>view</a>" if st
                              else f"<span class='st miss'>{label}: missed</span>" if ms else f"<span class='st'>{label}: scheduled</span>")
            badge = " ".join(badges)
            thr = p.get("threads") or {}
            th_html = ("<pre style='border-top:1px solid #233049;padding-top:8px'>Threads"
                       + (f" · topic: {esc(thr.get('topic') or '')}" if thr.get("topic") else "") + "\n\n" + esc(thr.get("text", ""))
                       + "".join("\n\n↳ " + esc(r) for r in thr.get("replies", [])) + "</pre>") if thr else ""
            imgs = "".join(f"<img loading='lazy' src='{esc(p['week'])}/{esc(p['id'])}/{esc(f)}'>" for f in p["files"])
            out.append(f"<div class='post'><b>{esc(p['scheduled_local'])}</b> · {esc(p['format'])} · {len(p['files'])} slides {badge}"
                       f"<div class='row'>{imgs}</div><pre>{esc(p['caption'])}</pre>{th_html}</div>")
    out.append("</body></html>")
    return "".join(out)


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default=str(ROOT / "site" / "topics.json"))
    ap.add_argument("--assets", required=True, help="checkout of the social-assets branch (or any output dir)")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--week", help="ISO week like 2026-W47 (default: current week in the configured timezone)")
    ap.add_argument("--now", help="pretend current local time, ISO format (testing)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    cfg = load_json(Path(a.config))
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=tz) if a.now else dt.datetime.now(tz)
    today = now.date()
    wk = a.week or week_key(today)
    monday = week_monday(wk)
    assets = Path(a.assets)
    assets.mkdir(parents=True, exist_ok=True)
    data = load_json(Path(a.topics))
    edition = data["meta"].get("edition", "")
    state = load_json(assets / "state.json", {"posted": {}, "missed": {}, "featured": {}})
    qpath = assets / "queue" / f"{wk}.json"
    old = load_json(qpath)

    def gh_out(changed: bool):
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"changed={'true' if changed else 'false'}\n")

    if old and old.get("edition") == edition and not a.force:
        print(f"{wk}: queue already built from edition {edition}; nothing to do.")
        gh_out(False)
        return 0
    if old:  # rebuilding: forget this week's own deep-dive picks so they can be re-chosen
        for tid in old.get("deep_dive_ids", []):
            if state["featured"].get(tid, {}).get("week") == wk:
                state["featured"].pop(tid)

    fd = data["meta"].get("freshnessDays", {})
    fresh, picks = pick_topics(data, state, monday, cfg)
    recent = [t for t in fresh if (today - d(t["published"])).days <= fd.get("fresh", 30)]
    brief_topics = recent[:5] if len(recent) >= 2 else picks
    fresh_ids = {t["id"] for t in fresh}

    posts = []
    renderer = None
    if not a.no_render:
        sys.path.insert(0, str(HERE))
        from render import Renderer
        renderer = Renderer().__enter__()
    try:
        for slot in cfg["schedule"]:
            fmt = slot["format"]
            built = None
            topic_ids = []
            if fmt == "weekly_brief" and brief_topics:
                built = weekly_brief(brief_topics, cfg, today, fd, monday, len(recent) >= 2); topic_ids = [t["id"] for t in brief_topics]
            elif fmt == "deep_dive" and slot.get("slot", 0) < len(picks):
                t = picks[slot["slot"]]
                built = deep_dive(t, cfg, today, fd, vault=t["id"] not in fresh_ids); topic_ids = [t["id"]]
            elif fmt == "quiz":
                built = quiz(picks, cfg, monday); topic_ids = [t["id"] for t in picks]
            elif fmt == "by_the_numbers":
                built = by_the_numbers(picks + [t for t in fresh if t not in picks], cfg); topic_ids = [t["id"] for t in picks]
            elif fmt == "terms":
                built = terms(picks, cfg); topic_ids = [t["id"] for t in picks]
            if not built:
                print(f"  skip {slot['day']} {fmt}: not enough material")
                continue
            slides, cap, th = built
            pid = f"{wk}-{slot['day']}"
            hh, mm = map(int, slot["time"].split(":"))
            when = dt.datetime.combine(monday + dt.timedelta(days=DAYS.index(slot["day"])), dt.time(hh, mm), tz)
            when += dt.timedelta(minutes=jitter(pid, cfg["jitter_minutes"]))
            out_dir = assets / wk / pid
            if out_dir.exists():
                shutil.rmtree(out_dir)
            files = []
            if renderer:
                files = renderer.render(slides, out_dir, cfg["handle"], cfg["app_name"])
            posts.append({
                "id": pid, "week": wk, "format": fmt, "topics": topic_ids,
                "scheduled_at": when.astimezone(dt.timezone.utc).isoformat(),
                "scheduled_local": when.strftime("%a %b %d, %I:%M %p %Z"),
                "caption": cap, "threads": th, "files": files,
                "urls": [f"{cfg['assets_base_url']}{wk}/{pid}/{f}" for f in files],
            })
            print(f"  {pid}: {fmt:15s} {len(slides)} slides at {posts[-1]['scheduled_local']}")
    finally:
        if renderer:
            renderer.__exit__(None, None, None)

    for t in picks:
        state["featured"][t["id"]] = {"week": wk, "version": t.get("version", 1)}
    save_json(qpath, {"week": wk, "edition": edition, "built": now.isoformat(timespec="minutes"),
                      "deep_dive_ids": [t["id"] for t in picks], "posts": posts})

    # keep only the newest few weeks of images and queues
    keep = sorted(p.stem for p in (assets / "queue").glob("*.json"))[-cfg["keep_weeks"]:]
    for p in (assets / "queue").glob("*.json"):
        if p.stem not in keep:
            p.unlink()
    for p in assets.glob("*-W*"):
        if p.is_dir() and p.name not in keep:
            shutil.rmtree(p)
    save_json(assets / "state.json", state)
    queues = [load_json(assets / "queue" / f"{k}.json") for k in reversed(keep)]
    (assets / "index.html").write_text(preview_html(queues, state), encoding="utf-8")
    (assets / ".nojekyll").write_text("")
    print(f"{wk}: built {len(posts)} posts from edition {edition}.")
    gh_out(True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
