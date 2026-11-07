# OAuth and persistence recheck — 2026-11-04

This is a sanitized operational update for the production-tracked branch. It contains no account identifiers, OAuth credentials, database credentials, or user records.

## Verified

- Render reports the main free Streamlit service's current commit as live. A fresh page load showed the authenticated assistant interface and its safe sign-out control. This verifies the page-level login gate; no model request was sent.
- Google OAuth is configured as an External app in Testing. It currently has one test user. The app is usable by that test account; general access remains limited.
- The Google branding page has the app name, support contact, and hosting domain. Homepage, privacy-policy, and terms links remain empty, and the Publish app control is disabled.
- A free Neon PostgreSQL project and ready development branch already exist. Metadata-only inspection found the assistant memory and CANO task tables. Row-level security is disabled on the current tables and there are no row policies, so the existing runtime database role is not a safe production connection for these user-scoped records.
- The Render free PostgreSQL instance is temporary and expires on 2026-12-02; it should not be treated as the long-term persistence option.
- The local project suite passed 229 tests and 46 subtests. Dependency consistency, Python compilation, and whitespace checks passed.

## Remaining work

1. Provide accurate public homepage, privacy, and terms pages under a domain that Google accepts; then review the OAuth audience and publish/verification requirements.
2. Before connecting the production app to Neon, provision a dedicated least-privilege runtime role and enforce per-user row isolation. Do not reuse the broad existing role.
3. Back up and compare any existing user-controlled records before enabling server-side persistence. No records were read, copied, or changed during this audit.

No paid service, production database change, model API request, or data migration was performed. Neutron-star research was not touched.
