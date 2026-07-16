# Cool TravelPal X automation

The `Post blog stories to X` GitHub Actions workflow publishes at 9:17 a.m.,
1:17 p.m., and 6:17 p.m. in `America/Los_Angeles`. GitHub hosts the job, so the
owner's Mac and Codex app do not need to be running.

## Required X setup

Create an X Developer Project and App for `@cooltravelpal`, enable read and
write access, and generate OAuth 1.0a user credentials for that account. Add
these four repository secrets under **Settings → Secrets and variables →
Actions**:

- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

Never add credential values to this repository or to workflow logs.

## Test before activating

1. Open **Actions → Post blog stories to X → Run workflow**.
2. Keep **Preview without publishing** enabled and run each of the three slots.
3. Review the generated copy in the workflow log.
4. Run the morning slot once with preview disabled to publish a real test.
5. Add the repository variable `X_AUTOMATION_ENABLED` with the value `true`.
6. After that succeeds, disable the three local Codex X automations to prevent
   duplicate posts.

Until `X_AUTOMATION_ENABLED` is set to `true`, scheduled runs validate and show
the selected post but do not publish it. A manual run with preview disabled can
still publish the one requested test post.

## Content behavior

The workflow reads checked-in titles and teasers from `blog/index.html`. It
does not ask an AI model to write posts at runtime. A small set of launch posts
has custom copy in `scripts/post_to_x.py`; all other posts use the article's
published title and teaser. The queue cycles through all articles and rotates
AI/apps, travel, experiences, and cards/points.

GitHub scheduled workflows can run late during periods of high load. The
schedule intentionally uses minute 17 rather than the top of the hour.
