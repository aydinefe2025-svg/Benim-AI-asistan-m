# CANO bounded task executor — local experimental capability

This component is a **finite offline task processor**, not a self-replicating autonomous
agent and not evidence of general intelligence or scientific discovery. It does
not alter any existing digital-genome checkpoint or the scheduled calendar.

## Run a real local batch

From repository root, create `jobs.json` with:

```json
{"jobs":[
  {"type":"csv_mean","values":[2,4,6]},
  {"type":"unit_conversion","amount":1.75,"from":"kg","to":"g"},
  {"type":"json_nested_lookup","data":{"run":{"count":9}},"path":["run","count"]}
]}
```

Run `python -m organism_lab.verified_task_batch --input jobs.json`. On Windows
`py -3.12 -m organism_lab.verified_task_batch --input jobs.json` uses an installed
Python interpreter. Alternatively use `--input -` to read JSON from stdin.

Each result includes the computed value and a SHA-256 job digest.
**Status `computed_unverified` does not imply independent validation**.
Unsupported, ambiguous or unsafe jobs fail closed. Identical inputs within
one batch are deduplicated; there is no persistent worker, service or timer.

## Safety and strict bounds

- At most 32 requests and 64 KiB of JSON per batch.
- Supported: CSV means, JSON lookups, dimensional length/mass conversion,
  exact linear regression, a single statically recognized Python error, and
  literal/metadata source checks. The implementation does not run submitted
  scripts, shell commands, processes, code patches or web requests.
- The repair check uses static AST structure; model output is never executed.
- Source-citation booleans only verify the caller-provided review metadata
  and literal string match, **not** independent peer-reviewed publication status.
- Booleans and numbers must not be interchangeable in the verification gate.
- An optional local Ollama candidate can be compared with a deterministic
  result using `verified_task_runner.run_job(..., prefer_local_model=True)`.
  The candidate does not override the deterministic computation.
- Successful fixed-schema computations are **not** proof of unbounded
  self-improvement, learning or physical robot/cell behavior.

## Tests

- `python -m unittest discover -s organism_lab/tests -v`
- `python -m organism_lab.bounded_task_benchmark`

The research benchmark uses fixed-schema deterministic tasks. New model
performance and genuine unseen-domain adaptation need separate holdouts;
do not promote old examples or local tests to general learning claims.

GitHub Actions `.github/workflows/organism-lab.yml` installs Streamlit
and runs the existing suite on Python 3.11/3.12 when the PR changes this folder.
