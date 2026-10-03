# TravelPal.now weekly newsletter

Send Saturday at 09:00 America/Los_Angeles, first regular issue October 10, 2026. The user authorized the October 3 test to both existing subscribed addresses (both belong to the user), then regular weekly delivery to newsletter subscribers.

The existing website publish workflow compiles and uploads a seven-day draft artifact; no new GitHub workflow or paid discovery requests. Run `python3 scripts/weekly_digest.py` for HTML and provenance JSON. Latest finalized revisions win; inactive stories and repeated story IDs are excluded. Do not pad quiet weeks with old articles or call an empty edition a full week of news. Links retain original sources and the published brief. Only use already published briefs and their verified facts.

A Codex thread heartbeat transfers the draft to EmailOctopus's campaign editor and sends it. EmailOctopus's current API does not create campaigns, so this is a browser delivery step, not a GitHub-to-email API integration. Desktop must be available and EmailOctopus signed in. On auth failure, leave the draft and report the blocker; never claim sending succeeded without dashboard evidence.

Free Starter only: no paid plans, trials, add-ons, extra users or removal of provider branding. Before sending verify current subscribed contacts <= 2500 and monthly sends + this issue <= 10000. Capacity must be available, not assumed. Stop and notify if a send would exceed either limit. At 2500 contacts, five weekly sends exceed the monthly allowance; skip rather than upgrade. Retain unsubscribe and sender address merge fields plus provider branding.

Use a unique campaign name TravelPal.now Weekly YYYY-MM-DD. Check existing campaigns and local send ledger before sending; never duplicate a sent or scheduled issue, including after timeouts. Save campaign ID, period, story IDs, content digest and confirmed status to the local ledger and outputs. Follow any new user corrections before the next edition. No newsletter sends on other days without authorization.
