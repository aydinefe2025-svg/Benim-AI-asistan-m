# Knowledge store: provenance-first research notes

The `KnowledgeStore` uses the same SQLite database path as `TaskStore` by default, so tasks and knowledge can share a local database file.

## Sources
Each source records its canonical URL, title, publisher, publication date (when known), access time, optional SHA-256 of supplied text, and notes. Re-adding the same URL updates that source record rather than creating a duplicate.

## Claims
Every stored claim must link to at least one known source. Each source link is labelled `supports`, `contradicts`, or `context`. A claim can be `unreviewed`, `supported`, `contested`, or `rejected`; confidence is a 0–1 bookkeeping field, not a calibrated probability.

## Important limitation
Recording a source does not mean it has been read or independently validated. A future ingestion/verification adapter must fetch the actual content, validate publisher identity and dates, preserve the retrieved snapshot/hash, and require a reviewer/test before moving a claim to a stronger status.
