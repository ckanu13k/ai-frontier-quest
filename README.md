# AI Frontier Quest

Install it on your phone: open the live site, then use Add to Home Screen (iPhone: Share > Add to Home Screen; Android/desktop Chrome: Install app).

Learn the week's most important AI and ML research by playing it. Each topic is a short briefing synthesized from lab blogs and published papers, followed by a quiz, recall cards and a timed term match. The Arcade adds a weekly Boss Battle, a 60-second Blitz, a Daily Challenge and a spaced-repetition Review deck.

**Live:** https://ckanu13k.github.io/ai-frontier-quest/

## How it works

- `site/index.html`: the whole app (vanilla HTML, CSS and JS; no build step, no dependencies). Responsive app shell: sidebar on desktop, top bar and bottom tabs on phones.
- `site/manifest.webmanifest`, `site/sw.js`, `site/icons/`: installable PWA. The service worker caches the app shell for offline use and fetches `topics.json` network-first, so weekly content shows up as soon as you're online.
- `site/topics.json`: all content. The app fetches it at load time.
- `scripts/validate_topics.py`: schema and sanity checks. CI runs it before every deploy, so a malformed content update never goes live.
- `.github/workflows/deploy.yml`: on every push to `main`, validates the content and deploys `site/` to GitHub Pages. Pull requests get validation only.

Player progress (XP, badges, Review deck) is stored in the browser's localStorage, so it stays on the device and browser where it was earned.

## Weekly content updates

A scheduled Claude task runs every Monday at 5:17 AM Central. It researches the past week's AI/ML work, then edits `site/topics.json`:

- adds 2 to 3 new topics
- refreshes topics with material new developments (bumps `version`, updates `published` and `lastReviewed`)
- archives non-classic topics more than 240 days old with no updates (`status: "archived"`; they stay playable)
- prepends a `changelog` entry

It runs the validator, commits to `main`, and the workflow redeploys the site.

## Topic schema

Each entry in `topics[]`:

| Field | Notes |
|---|---|
| `id` | kebab-case, unique |
| `title`, `tagline`, `summary`, `whyItMatters` | plain prose |
| `category` | must appear in `meta.categories` |
| `difficulty` | 1 Intro, 2 Core, 3 Deep |
| `published` | date of the newest source; drives the Fresh/Current/Aging/Stale label |
| `added`, `lastReviewed` | ISO dates |
| `version` | bump on every material rewrite; players get full XP again |
| `status` | `active` or `archived` |
| `classic` | `true` for background topics that never go stale |
| `keyIdeas` | 3 to 6 strings |
| `numbers` | `{value, label, verified}`; `verified: false` shows a "Reported" tag |
| `sources` | `{title, publisher, date, url}` |
| `quiz` | exactly 5 `{q, options[4], answer (0-3), explain}` |
| `cards` | exactly 5 `{term, def}` |

## Run locally

```bash
python scripts/validate_topics.py
cd site && python -m http.server 8000
# open http://localhost:8000
```
