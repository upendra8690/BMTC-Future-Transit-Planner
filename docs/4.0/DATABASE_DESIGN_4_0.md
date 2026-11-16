# Database design for 4.0

All changes are Alembic migrations after `0002`. Nothing existing is dropped. SQLite for development and tests;
Postgres (decision D3) for production. CI will run migrations and tests on both.

## Existing tables (kept)
`data_sources`, `verification_records`, `gtfs_imports`, `agencies`, `routes`, `stops`, `service_calendars`,
`service_exceptions`, `trips`, `stop_times`, `shape_points`, `fare_attributes`, `fare_rules`, `scenarios`,
`scenario_stops`, `saved_routes`, `user_preferences`, `audit_logs`.

## New tables by phase

| Migration | Phase | Tables / columns | Notes |
|---|---|---|---|
| `0003_gtfs_extras` | 2, 4 | `stops`: `location_type`, `parent_station`, `wheelchair_boarding`, `platform_code`; `routes`: `route_color`, `route_text_color`; new `transfers` (from `transfers.txt`) | Enables Metro stations, interchanges, accessibility |
| `0004_feature_flags` | 1 | `feature_flags(key, state, reason, updated_by, updated_at)` | Drives `/api/features` |
| `0005_facilities` | 6 | `facilities(id, kind, name, lat, lon, source, source_ref, licence, attributes JSON, updated_at)`; `route_tags(route_id, tag)` (e.g. `airport`) | OSM imports keep the source and licence |
| `0006_accounts` | 5 | `users(id, email UNIQUE, password_hash, display_name, language, created_at, deleted_at)`; `sessions(id_hash, user_id, csrf_hash, expires_at, created_at, ip_hash)`; `favourite_stops`, `saved_journeys(user_id, request JSON, label)`, `recent_searches(user_id, query, kind, created_at)`; `saved_routes` and `user_preferences` gain nullable `user_id` | Device data can be moved into an account |
| `0007_notifications` | 5 | `push_subscriptions(user_id/device, endpoint, keys, created_at)`, `notification_settings` | Web Push only |
| `0008_realtime` | 3 | `vehicle_positions(feed_id, vehicle_ref, trip_id, route_id, lat, lon, bearing, observed_at, received_at)`; `trip_updates(...)`; `provider_status(provider, state, last_ok_at, last_error)` | Short retention (see below) |
| `0009_admin_rbac` | 10 | `admin_users(user_id, role)`; `security_events(kind, detail, created_at)` | Roles: viewer, editor, admin |
| `0010_commerce_schema` | 7 | `orders`, `tickets`, `payment_events(provider_event_id UNIQUE, signature_ok, payload_hash)`, `idempotency_keys` | **Schema only**; no provider is active. No card, CVV or UPI PIN columns exist. |

## Data retention

| Data | Kept for | Reason |
|---|---|---|
| Vehicle positions | 24 hours | Live view only |
| Sessions | Until expiry (30 days) or logout | Security |
| Recent searches | 90 days, user can clear | Convenience |
| Audit logs, security events | 1 year | Accountability |
| Deleted accounts | Personal fields removed at deletion; audit rows keep only a hashed user id | Privacy |
| Location | **Never stored server-side** unless the user saves a place | Privacy |
