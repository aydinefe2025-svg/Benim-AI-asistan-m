# CANO Render PG18 private-network probe — reviewed planning only

**Not a database backup. Not an approved deploy.**

This prototype is an isolated Frankfurt **Free** web-service plan to prove
that Render's private PostgreSQL connection reference can reach the
specific expiring Render PG18 database without opening its external IP
allowlist or revealing connection passwords. The application issues just
one metadata-only read-only SELECT at startup, and exposes only a redacted
HTTP /healthz status. HTTP requests cannot trigger a dump or any write.
No user data, SQL tables, secret, dump or upload is processed.

## Reproducible tests
- \`python -m unittest tests.test_cano_cloud_readonly_probe -v\`
- No actual database or Render account is touched by these synthetic tests.
- A green test/Blueprint plan never proves real pg_dump, offsite receipt or
  isolated recovery. All three remain OPEN in GitHub issue #440.

## Non-deploying infrastructure plan
1. Confirm Blueprint YAML exists on the isolated review branch:
   \`deploy/render-cano-private-readonly-probe.yaml\`.
2. Call Render \`create_blueprint\` with existingResources=\`create_new\`,
   autoSync=false, branch=this exact review branch and path=this YAML.
3. Review returned planningOutcome, resources, plan costs, notices,
   required secrets and provider status. Do not approve or deploy.
4. Only after separate operator approval may the *new* probe service be
   created. This would test connectivity alone, not restore the DB.

A future actual cloud exporter would additionally need owner-controlled
backup key, an independently durable offsite destination with least-
privilege write/read access, pg_dump 18 executable, authentication/readback
and isolated restore. It must not deploy the legacy owner-only CLI onto
ephemeral Render disk unchanged.

Sources: https://render.com/docs/blueprint-spec ,
https://render.com/docs/free ;
https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/440 .
