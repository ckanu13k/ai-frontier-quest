# Instagram + Threads autopilot

Turns each weekly AI Frontier Quest refresh into 7 branded carousels and posts one a day at a different time, to Instagram and to Threads. After the one-time setup below, there is nothing to do day to day.

## Current mode: one post a week (Wednesdays, 12:10 PM Central)

`"mode": "weekly"` in `config.json` folds the week into a single post:
- **Instagram:** one 10-slide carousel. Meta's API caps carousels at 10. It has an opener, each deep dive's cover and "In practice" slide, the week's numbers, a quiz question (answer in the caption) and a call to action. The caption lists the deep dives with their real-world uses.
- **Threads:** Monday's brief is the top post. Tuesday through Sunday follow as comments, in order, each with that day's full carousel. A last comment links to the app.

The day-by-day pieces below are still built; weekly mode composes them. Set `"mode": "daily"` to go back to one post per day. Change the day and time under `"weekly"`.

To publish a week by hand, run Actions → **Social - publish** with post ids `2026-W47-weekly`.

## How it runs

| When | What | Workflow |
|---|---|---|
| Monday, right after the weekly content commit lands | Builds the week: picks topics, writes captions, renders 1080x1350 slides, saves the queue | `social-build.yml` |
| Every 20 minutes | Posts whatever is due, to Instagram and Threads independently (most runs do nothing) | `social-publish.yml` |
| Wednesdays | Extends the 60-day Threads token and saves it back (the Instagram system-user token never expires) | `social-token.yml` |

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

### How posts look on Threads
Same slides, as a carousel, plus Threads-native text. Threads caps posts at 500 characters (counted as UTF-8 bytes, so an emoji costs up to 4), and links there are clickable, unlike Instagram captions:
- **Main post:** short hook (title, tagline, why it matters), with one topic tag per post (`threads_topics` in `config.json`)
- **Replies chained under it:** "💡 In practice: …", then a direct link to the app plus sources
- Quiz, numbers and glossary posts get the list itself and a link reply

Instagram and Threads keep separate records. A slot that passed before a platform was connected is skipped without an error.

## One-time setup (about 30 minutes)

### 1. Instagram account
1. Create the dedicated account (the slides say `@aifrontierquest`; change `handle` in `config.json` if you pick another).
2. Switch it to a **Professional** account (Business or Creator) and keep it **public**. Settings → Account type and tools.
3. Profile: put the app link (`https://frontierquest.vercel.app`, set as `app_url` in `config.json`) in the Instagram and Threads bios, because every caption says "link in bio."

### 2. Meta app (done Nov 17, 2026)
Already set up: app **AI Frontier Quest Social** (App ID 1128932373224847), business portfolio **AI Frontier Quest**, use case *Manage messaging & content on Instagram* with **API setup with Unified login**. Meta no longer offers the older "Instagram login" setup to new apps. `@aifrontierquest` (Instagram ID 17841459473104306) is an accepted Instagram Tester.

To make a new token later: developers.facebook.com → the app → Use cases → Instagram API → Customize → API setup with Unified login → **2. Generate access tokens** → **Generate token**. Click it yourself: Meta opens a sign-in window that only your own click can open. It is a **system-user token that never expires**, so there's nothing to refresh.

### 2b. Threads (same Meta app)
The app also has the **Access the Threads API** use case, with `threads_basic` and `threads_content_publish`.
1. The Threads profile for `@aifrontierquest` must exist and be public (create it in the Threads app: Switch profiles → Add profile → aifrontierquest).
2. App roles → Roles → Add People → **Threads Tester** → `aifrontierquest`, then accept the invite in Threads (Settings → Account → Website permissions → Invites).
3. Use cases → Access the Threads API → Customize → Settings → **User Token Generator** → Generate token (click it yourself), then copy the token.
4. Save it as the `THREADS_ACCESS_TOKEN` secret. It lasts 60 days, so also add `GH_SECRETS_PAT` (below) so the Wednesday job can extend it automatically.

### 3. GitHub secrets
Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the token from step 2 |
| `IG_USER_ID` | `17841459473104306` (also in `config.json` as `ig_user_id`) |
| `THREADS_ACCESS_TOKEN` | the Threads token from step 2b |
| `GH_SECRETS_PAT` | a fine-grained personal access token limited to this repo, with **Secrets: Read and write**. Lets the Wednesday job save the refreshed Threads token. Give it the longest expiry GitHub allows and set a renewal reminder: this is the only recurring chore |

### 4. Turn it on
1. Actions tab → **Social - build week** → Run workflow (tick *force*). The slides are then viewable at `https://ckanu13k.github.io/ai-frontier-quest/social/`.
2. Actions → **Social - publish** → Run workflow with *check* ticked. The log should say `Instagram OK: @aifrontierquest` and `Threads OK: @aifrontierquest`. Then run it with *dry run* ticked to see which post it would publish next.
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
- `publish.py`: posts due items to Instagram (auto-detects the token type: `EAA…` via graph.facebook.com, `IG…` via graph.instagram.com) and to Threads (graph.threads.net: carousel plus a chained reply thread), with a double-post guard on each
- `refresh_token.py`: 60-day token extension (Threads, or Instagram Login tokens)
- `scripts/assets.sh`: syncs the `social-assets` branch, which is kept as a single commit so images never pile up in history
- `fonts/`: Sora, Plus Jakarta Sans and JetBrains Mono (SIL Open Font License)

Run locally: `pip install -r social/requirements.txt && python -m playwright install chromium && python social/build_week.py --assets /tmp/social-preview`, then open `/tmp/social-preview/index.html`.
