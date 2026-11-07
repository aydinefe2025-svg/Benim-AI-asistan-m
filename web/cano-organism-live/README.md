# CANO Live Organism Observatory — public simulation monitor

This page renders only public, synthetic, reproducible organism simulation records from the isolated GitHub state branch. It performs independent browser SHA-256 checks before showing any numeric state, compares the saved observations to division-disabled controls, and never creates organisms or runs a model in the browser. Refreshes the state every 90 seconds. If data cannot be verified, shows an explicit error instead of fabricated or cached metrics.

Published using a free Render static site via GitHub source branch; not the existing production Render CANO service. No keys, owner data, personal data, model APIs, public write endpoints or physical actuation.

**Source branch**: `feature/cano-live-organism-observatory-20261107`.
**State branch**: `experiment/cano-digital-state-20261107`.
**Real computation**: `main:.github/workflows/cano-digital-organism-calendar.yml` scheduled once daily at `05:47 UTC`; GitHub job writes to state branch when successful. The scheduled action is not proven to have executed just because this monitor is live. A public monitor does not imply an autonomously training agent, sentience, biological life or self-building robotics.

**Build on Render**: command `mkdir -p public && cp web/cano-organism-live/index.html public/index.html`, publish path `public`.
