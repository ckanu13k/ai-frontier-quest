# Instagram autopilot

Turns each weekly AI Frontier Quest refresh into 7 branded Instagram carousels and posts one a day at a different time. After the one-time setup below, there is nothing to do day to day.

## How it runs

| When | What | Workflow |
|---|---|---|
| Monday, right after the weekly content commit lands | Builds the week: picks topics, writes captions, renders 1080x1350 slides, saves the queue | `social-build.yml` |
| Every 20 minutes | Posts whatever is due (most runs do nothing) | `social-publish.yml` |
| Wednesdays | Extends the Instagram token another 60 days and saves it back as a secret | `social-token.yml` |

Everything posted comes from `site/topics.json`: titles, briefings, key ideas, numbers (unverified ones carry a REPORTED tag), quiz questions, term cards and sources. No new claims are written.

### The weekly lineup (Central time; each slot shifts by up to ±12 min so posts don't land on the same minute every week)

| Day | Time | Format | Why it works |
|---|---|---|---|
| Mon | 7:45 AM | **Weekly brief**: everything new this week, one slide each | Sets up the week; good for follows |
| Tue | 12:15 PM | **Deep dive #1**: what happened, 4 key ideas, numbers, why it matters, sources | Save-worthy; strongest ad candidate |
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

### 2. Meta app (gives you the posting token)
Meta renames these menus often; the docs page is "Create a Meta App for Instagram Platform."
1. Go to developers.facebook.com → My Apps → **Create app**. Choose the use case **Manage messaging & content on Instagram**.
2. Open the use case → **API setup with Instagram login**. Make sure the permissions include `instagram_business_basic` and `instagram_business_content_publish`.
3. **Add your Instagram account.** In development mode only accounts with an app role can get a token: App roles → Roles → Add People → **Instagram Tester**, then accept the invite in Instagram (Settings → Apps and websites → Tester invites). If Meta refuses with "role on the app's owning business," switch the app to **Live** instead. Posting to your own account does not need App Review.
4. Under **Generate access tokens**, click **Generate token** next to the account and copy it right away (it's shown once).

### 3. GitHub secrets
Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the token from step 2.4 |
| `IG_USER_ID` | optional; it's looked up automatically if left out |
| `GH_SECRETS_PAT` | a fine-grained personal access token, limited to this repo, with **Secrets: Read and write**. Lets the weekly job save the refreshed Instagram token. Give it the longest expiry GitHub allows and set yourself a renewal reminder. This is the only recurring chore. |

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
- `publish.py`: posts due items through the Instagram API with Instagram Login and guards against double posts
- `refresh_token.py`: 60-day token extension
- `scripts/assets.sh`: syncs the `social-assets` branch, which is kept as a single commit so images never pile up in history
- `fonts/`: Sora, Plus Jakarta Sans and JetBrains Mono (SIL Open Font License)

Run locally: `pip install -r social/requirements.txt && python -m playwright install chromium && python social/build_week.py --assets /tmp/social-preview`, then open `/tmp/social-preview/index.html`.
