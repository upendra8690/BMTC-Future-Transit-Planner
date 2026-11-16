# Data retention policy

| Data | Retention commitment | Implemented in software? |
|---|---|---|
| Device-linked saved routes, scenarios, preferences | Until the person deletes them or uses "Delete my data" | Yes (manual deletion and erasure endpoint) |
| Device data not used for 12 months | Delete | **No — gap.** Needs a scheduled job; planned with accounts |
| Browser-only lists (favourites, recent searches) | Until cleared on the device | Yes (cleared by the person or by "Delete my data") |
| Location coordinates | Not stored by the app | Yes; request access log disabled in the container |
| Search text | Not stored by the app | Yes; request access log disabled in the container |
| Audit log (admin data changes, erasure counts) | 1 year | **No — gap.** No automatic deletion yet |
| Timetable feeds | While in use; removed when superseded or withdrawn | Yes (admin delete) |
| Database backups | 30 days | **No — gap** for hosted deployments; to be configured with the Postgres provider |
| Hosting-provider logs | Under the provider's own policy | Outside the app's control |

The gaps are listed so that they are fixed before any pilot that involves members of the public.
