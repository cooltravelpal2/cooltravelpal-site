# Cool TravelPal X automation

The `Post blog stories to X` GitHub Actions workflow selects content at 8:17
a.m., 12:17 p.m., and 5:17 p.m. in `America/Los_Angeles`. Buffer then publishes
at 9:00 a.m., 1:00 p.m., and 6:00 p.m. GitHub hosts the job, so the owner's Mac
and Codex app do not need to be running.

Publishing goes through Buffer's Free plan rather than X's paid developer API.
Buffer allows up to 10 queued posts per connected channel on the Free plan. The
workflow adds one post shortly before each Buffer publishing slot, so the queue
normally remains well below that limit.

## Required Buffer setup

1. Create a free Buffer account and verify its email address.
2. Connect the `@cooltravelpal` X profile as a Buffer channel.
3. Set Buffer posting times for 9:00 a.m., 1:00 p.m., and 6:00 p.m. Pacific.
4. In Buffer, open **Settings → API → Personal Keys → New Key**.
5. Name it `CoolTravelPal GitHub Automation`, keep the account/channel read and
   post-creation permissions, and choose the longest available expiration.
6. Add the key to this GitHub repository as the secret `BUFFER_API_KEY` under
   **Settings → Secrets and variables → Actions**.

Never add the key value to this repository, workflow logs, or chat messages.

## Test before activating

1. Open **Actions → Post blog stories to X → Run workflow**.
2. Keep **Preview without publishing** enabled and run each slot.
3. Review the generated copy in the workflow log.
4. Run the morning slot once with preview disabled. This adds one post to
   Buffer; confirm its text and scheduled time in Buffer.
5. Set the repository variable `X_AUTOMATION_ENABLED` to `true`.
6. Disable the three local Codex X automations to prevent duplicate posts.

Until `X_AUTOMATION_ENABLED` is `true`, scheduled runs validate and show the
selected post but do not add it to Buffer. A manual run with preview disabled
can still create the requested test post.

## Content behavior

The workflow reads checked-in titles and teasers from `blog/index.html`. It
does not ask an AI model to write posts at runtime. A small set of launch posts
has custom copy in `scripts/post_to_x.py`; all other posts use the article's
published title and teaser. The queue cycles through all articles and rotates
AI/apps, travel, experiences, and cards/points.

GitHub scheduled workflows can run late during periods of high load. The
schedule intentionally uses minute 17 rather than the top of the hour.
