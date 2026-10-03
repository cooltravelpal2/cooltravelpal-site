# TravelPal.now daily travel briefs

The feed server owns collection, shared editorial criteria, and canonical edition
facts. The site validates, archives and renders those facts; it does not search
or call an LLM to write a second account.

Enable `TRAVEL_BRIEFS_ENABLED=true` as a repository variable only after the server's
shared policy and brief API have been verified. Existing `publish-site.yml`
checks for finalized editions, archives validated JSON under `data/travel-briefs/`,
commits that directory with the workflow token, builds the site and deploys in
the same run. Its morning slot is now 07:30 Pacific. No workflow was added.
Repository write permission is needed by the existing publish job for snapshots;
the X job remains read-only. Verify branch protection permits constrained bot
commits before enabling archive publication. A rejected push prevents deployment.

Generated articles: `/blog/travel-brief-YYYY-MM-DD/`. Archive: `/travel-briefs/`.
Manifest: `/daily-travel-brief.json`. Clean builds regenerate all archived dates.
No-news editions create no article. Source outages retain archived snapshots.
Private snapshot files are excluded from the deployed static root.

Manual workflow dry runs may fetch and write local snapshots in the runner, but
do not commit, push, deploy or write to Buffer. Local rendering can use test
fixtures; synthetic previews must never be placed in `data/travel-briefs/`.

After verifying a public edition, set `TRAVEL_BRIEF_X_ENABLED=true`. The existing
midday X slot prioritizes today's live article; evening provides a missed-midday
fallback. The live digest/revision must match the manifest. Buffer sent/queued
history suppresses repeats by canonical URL. Daily briefs are always excluded
from evergreen rotation. Morning exercise behavior is preserved. Uncertain
Buffer mutation outcomes require reconciliation; createPost is never blindly
retried. A provider-side exactly-once guarantee is not claimed.

Source permission pending, strict provider-tool budget bounds, and Azure database
backup/restore are rollout prerequisites documented in the feed repository.
