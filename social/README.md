# Instagram autopilot

Turns each weekly AI Frontier Quest refresh into 7 branded Instagram carousels and posts one a day at a different time. After the one-time setup below, there is nothing to do day to day.

## How it runs

| When | What | Workflow |
|---|---|---|
| Monday, right after the weekly content commit lands | Builds the week: picks topics, writes captions, renders 1080x1350 slides, saves the queue | `social-build.yml` |
| Every 20 minutes | Posts whatever is due (most runs do nothing) | `social-publish.yml` |
| Wednesdays | Only for 60-day Instagram Login tokens: extends it and saves it back. Exits immediately for the never-expiring token in use | `social-token.yml` |

Everything posted comes from `site/topics.json`: titles, briefings, key ideas, the `inPractice` real-world use, numbers (unverified ones carry a REPORTED tag), quiz questions, term cards and sources. No new claims are written.

### The weekly lineup (Central time; each slot shifts by up to ±12 min so posts don't land on the same minute every week)

| Day | Time | Format | Why it works |
|---|---|---|---|
| Mon | 7:45 AM | **Weekly brief**: everything new this week, one slide each | Sets up the week; good for follows |
| Tue | 12:15 PM | **Deep dive #1**: what happened, 4 key ideas, numbers, why it matters, **in practice** (a real-world use), sources | Save-worthy; strongest ad candidate |
| Wed | 6:40 PM | **Quiz**: 3 questions, answers on the next slide | Comments ("1B 2D 3A") drive reach |
| Thu | 8:10 AM | **Deep dive #2** | |
| Fri | 12:05 PM | **By the numbers**: the week's best verified figures | Shareable |
| Sat | 10:30 AM | **Glossary**: 6 terms in plain English | Saves |
| Sun | 7:20 PM | **Deep dive #3** (or "From the vault" if the week was light) | |

These times are common starting points, not tested for this account. After 3 to 4 weeks, check Instagram Insights ("Most active times") and change the times in `config.json`.

Topic rules: deep dives go to the newest topics first. A topic isn't deep-dived again for 8 weeks unless its `version` is bumped. Light weeks are filled from the back catalog, starting with the topics featured least recently.

## One-time setup (about 30 minutes)

### 1. Instagram account
1. Create the dedicated account (the slides say `@aifrontierquest`; change `handle` in `config.json` if you pick another).
2. Switch it to a **Professional** account (Business or Creator) and keep it **public**. Settings → Account type and tools.
3. Profile: put the app link (`https://ckanu13k.github.io/ai-frontier-quest/`) in the bio, because every caption says "link in bio."

### 2. Meta app (done Nov 17, 2026)
Already set up: app **AI Frontier Quest Social** (App ID 1128932373224847), business portfolio **AI Frontier Quest**, use case *Manage messaging & content on Instagram* with **API setup with Unified login**. Meta no longer offers the older "Instagram login" setup to new apps. `@aifrontierquest` (Instagram ID 17841459473104306) is an accepted Instagram Tester.

To make a new token later: developers.facebook.com → the app → Use cases → Instagram API → Customize → API setup with Unified login → **2. Generate access tokens** → **Generate token**. Click it yourself: Meta opens a sign-in window that only your own click can open. It is a **system-user token that never expires**, so there's nothing to refresh.

### 3. GitHub secrets
Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the token from step 2 |
| `IG_USER_ID` | `17841459473104306` (also in `config.json` as `ig_user_id`) |
| `GH_SECRETS_PAT` | not needed with a never-expiring token. Only for an Instagram Login token (starts with `IG`, lasts 60 days): a fine-grained token with **Secrets: Read and write** on this repo, so the weekly job can save the refreshed token |

### 4. Turn it on
1. Actions tab → **Social - build week** → Run workflow (tick *force*). The slides are then viewable at `https://ckanu13k.github.io/ai-frontier-quest/social/`.
2. Actions → **Social - publish** → Run workflow with *dry run* ticked. The log should say which post it would publish.
3. Optional check from a terminal: `IG_ACCESS_TOKEN=... python social/publish.py --check` prints the account name and publishing quota.

From then on it runs by itself. Slots that had already passed when the queue was built are skipped quietly. Posts that go out late within 6 hours are still published. Anything later is marked missed, and GitHub emails you about the failed run.

## Day to day

- **Nothing required.** If you want to look ahead, open `…/social/` to see the week's slides, captions, times and what has posted.
- **Pause:** Settings → Secrets and variables → Actions → Variables → `SOCIAL_PAUSED` = `true` (or set `"paused": true` in `config.json`).
- **Boost as an ad:** in the Instagram app, open a post → *Boost post*. Deep dives and the weekly brief work best. All slides are 4:5, the feed ad format.
- **Change times, hashtags or handle:** edit `config.json`. Pushing a change under `social/` rebuilds the current week.
- **Look and feel:** `render.py` (colors, fonts and layout match the app's dark theme).

## Files

- `config.json`: schedule, handle, hashtags, timezone, pause switch
- `build_week.py`: picks topics, writes captions, renders slides, writes the queue and preview page
- `render.py`: slide templates (HTML/CSS rendered by headless Chromium to JPEG)
- `publish.py`: posts due items through the Instagram API (auto-detects the token type: `EAA…` via graph.facebook.com, `IG…` via graph.instagram.com) and guards against double posts
- `refresh_token.py`: 60-day token extension (only for Instagram Login tokens)
- `scripts/assets.sh`: syncs the `social-assets` branch, which is kept as a single commit so images never pile up in history
- `fonts/`: Sora, Plus Jakarta Sans and JetBrains Mono (SIL Open Font License)

Run locally: `pip install -r social/requirements.txt && python -m playwright install chromium && python social/build_week.py --assets /tmp/social-preview`, then open `/tmp/social-preview/index.html`.
