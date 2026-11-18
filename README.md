# AI Frontier Quest

Install it on your phone: open the live site, then use Add to Home Screen (iPhone: Share > Add to Home Screen; Android/desktop Chrome: Install app).

Learn the week's most important AI and ML research by playing it. Each topic is a short briefing synthesized from lab blogs and published papers, followed by a quiz, recall cards and a timed term match. The Arcade adds a weekly Boss Battle, a 60-second Blitz, a Daily Challenge and a spaced-repetition Review deck.

**Live:** https://frontierquest.vercel.app/ (mirror: https://ckanu13k.github.io/ai-frontier-quest/)

## How it works

- `site/index.html`: the whole app (vanilla HTML, CSS and JS; no build step, no dependencies). Responsive app shell: sidebar on desktop, top bar and bottom tabs on phones.
- `site/manifest.webmanifest`, `site/sw.js`, `site/icons/`: installable PWA. The service worker caches the app shell for offline use and fetches `topics.json` network-first, so weekly content shows up as soon as you're online.
- `site/topics.json`: all content. The app fetches it at load time.
- `scripts/validate_topics.py`: schema and sanity checks. CI runs it before every deploy, so a malformed content update never goes live.
- `.github/workflows/deploy.yml`: on every push to `main`, validates the content and deploys `site/` to GitHub Pages. Pull requests get validation only.
- Vercel project `aiquest` (root directory `site`, no build step) also deploys every push to `main` and serves the primary address, https://frontierquest.vercel.app/.

Player progress (XP, badges, Review deck) is stored in the browser's localStorage, so it stays on the device and browser where it was earned.

## Accounts, personas and sync

- **Front page:** visitors who aren't signed in see a landing page (`#welcome`) with sign-up, log-in and a guest option.
- **Accounts:** Supabase Auth (email + password, email sign-in links, password reset) using the PKCE flow. Project: `pzmbbdvefyirzztibldp`. The publishable key in `site/index.html` is meant to be public; data is protected by Row Level Security.
- **Database:** `supabase/schema.sql` creates `public.profiles` (one row per user: name, persona, interests, daily goal and a `progress` JSON blob) with owner-only RLS policies and a sign-up trigger.
- **Personas:** onboarding asks for a track (Student or career switcher, Engineer or data scientist, Researcher, Leader or domain expert), interests and a daily goal. The track reorders each lesson (for example, leaders see "Why it matters" first, researchers see primary sources first, students get a key-terms glossary) and drives the "Recommended for you" row.
- **Sync:** progress is cached locally and pushed to `profiles.progress` a couple of seconds after each change. Guest progress is merged into the account on first sign-in.
- **Email:** email confirmation is off so sign-up works instantly. Supabase's built-in mailer only delivers to project team members, so sign-in links and password resets need a custom SMTP provider (for example Resend) before they work for the public.

## Weekly content updates

A scheduled Claude task runs every Monday at 5:17 AM Central. It researches the past week's AI/ML work, then edits `site/topics.json`:

- adds 2 to 3 new topics
- refreshes topics with material new developments (bumps `version`, updates `published` and `lastReviewed`)
- archives non-classic topics more than 240 days old with no updates (`status: "archived"`; they stay playable)
- prepends a `changelog` entry

It runs the validator, commits to `main`, and the workflow redeploys the site.

## Instagram autopilot

`social/` turns each weekly refresh into 7 branded Instagram carousels (weekly brief, 3 deep dives, a quiz, the week in numbers, a glossary) and posts one a day at varied times through the Instagram API, all from GitHub Actions. Setup and details: [social/README.md](social/README.md).

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
| `inPractice` | optional, 1 to 2 sentences (20 to 300 chars): a concrete real-world use and its availability. Shown in lessons under "Why it matters" and on Instagram deep dives |
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
