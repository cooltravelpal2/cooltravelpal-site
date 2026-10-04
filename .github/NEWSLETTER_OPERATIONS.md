# TravelPal.now weekly newsletter

Regular delivery: Saturday 09:00 America/Los_Angeles, starting October 10, 2026. GitHub schedules are best effort and may run late. The existing publish workflow deploys the website and then queues the weekly email through EmailOctopus's official v2 API. No new workflow, local scheduler, browser dependency, or paid discovery requests. The former local sender remains paused.

## Delivery and content

- `scripts/weekly_digest.py` compiles the latest finalized editions from a seven-day window. Withdrawn stories and repeated IDs are excluded. Select at most five highlights, at most two per topic, with topic coverage before extras. Empty weeks are not sent.
- The full illustrated weekly web edition is published at `/weekly/YYYY-MM-DD/`. Saturday editions are rebuilt from the finalized archive on later deployments so old newsletter links keep working and withdrawals remain reflected.
- `scripts/weekly_sender.py` inserts one brief plain-text paragraph per article into the native HTML template `templates/emailoctopus-weekly.html`. Colored article borders, small JPEG illustrations, sender details, unsubscribe and EmailOctopus branding are part of the template. Card-offer amounts, spending requirements, timing, fee and deadline stay together. Overlong offer content stops delivery for review.
- API automation `69b368be-bf90-11f1-a32d-2fff2da0bbd9` is TravelPal.now Saturday Weekly Edit, with Manually via API trigger and Allow contacts to repeat enabled. One email step, immediate delivery. Every article has its own Read full article link, using an immutable numbered weekly permalink that forwards to the matching blog article anchor. Numbered links and images are generated from a frozen public editorial snapshot in data/weekly-newsletter-issues. Snapshots are persisted before website deployment; later ranking changes cannot repoint a sent link. The sender rejects frozen content that has since changed or been withdrawn. Personalization must be previewed using a real subscriber; default previews use placeholders.
- Starter supports seven custom fields, each at most 600 characters. WeeklyHighlight1–5 each contain a single article paragraph, selected with topic coverage and at most two per topic. WeeklyPeriod contains the Saturday date. WeeklySendState is a private write-ahead send record. HTML custom fields are escaped and the `raw` filter is unsupported; do not reintroduce them.
- Encrypted GitHub secrets: EMAILOCTOPUS_API_KEY and EMAILOCTOPUS_TEST_CONTACT_IDS. Never expose credentials, addresses, contact IDs or private state in logs, artifacts or repository history.
- WEEKLY_NEWSLETTER_ENABLED=true enables regular delivery only on the existing Saturday cron. Pushes and ordinary manual builds never send. Owner preview preparation uses newsletter_preview=true and dry_run=false, updates only the two owner contacts, and never queues email. Explicit owner tests require workflow_dispatch newsletter_test=true and dry_run=false, and only send to the two configured owner contact IDs.

## Free plan and capacity

Free Starter only: no upgrades, trials, add-ons or removal of provider branding. Verified October 3: two subscribers, two of 10,000 sends used, reset October 16. Illustration template test sends did not increase the displayed quota.

The sender stops above 1,500 subscribed contacts, reserves each queue attempt before sending, and checks a private monthly ledger stored in the WeeklyPeriod field's fallback. The ledger uses the observed billing reset day (16), starts with the verified two sends, and leaves 2,500 sends reserved for welcome/manual traffic. It stops when reservations plus this issue plus that allowance exceed 10,000. Unknown queue outcomes retain both capacity and contact reservations; no automatic retry. EmailOctopus also enforces its account limits. The API does not expose live account-wide quota, so this ledger is a conservative reservation rather than a provider usage report. If manual/welcome traffic exceeds the 2,500 allowance, reconcile the baseline or pause delivery; do not silently assume additional capacity or upgrade. Recheck the reset day if the account plan changes.

Concurrent runs are serialized by the existing travelpal-pages workflow group. No second sender should write these fields. Only update existing subscribed contacts; never change status, address or re-subscribe a contact. Recheck subscription immediately before queueing, and retain the provider's normal unsubscribe enforcement.

Each contact is marked weekly:YYYY-MM-DD:pending before queueing and weekly:YYYY-MM-DD:queued only after a successful 204 response. A queued issue is skipped on rerun. A pending issue stops with an actionable workflow failure, including on later weeks, rather than risking a duplicate. A 204 means accepted into the automation, not proof of inbox delivery. Reconcile a pending contact against native automation reports before clearing it. Owner tests use a distinct weekly-test issue key.

## Daily blog

Daily publication was activated with user approval October 3. Azure CardPecker collects at 07:00 Pacific, finalizes qualifying editions, and the existing 07:30 website schedule synchronizes and publishes. The reviewed October 3 r1–r3 snapshots retain their original digests. Quiet days retain the archive. Source/quality monitoring continues; future daily runs are not considered verified until observed.

References: [official v2 API](https://emailoctopus.com/api-documentation/v2), [field limits](https://help.emailoctopus.com/article/37-adding-new-fields), [repeating automations](https://help.emailoctopus.com/article/379-repeating-an-automation).

The sender-address privacy toggle remains enabled. EmailOctopus therefore displays its London mail-forwarding address, not the saved private business address. Do not disable that toggle or expose the stored address without the user confirming a valid business mailing address for publication. The footer uses SenderInfoLine for a compact presentation; unsubscribe and provider branding remain present.
