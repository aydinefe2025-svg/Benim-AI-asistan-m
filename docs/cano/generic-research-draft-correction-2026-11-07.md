# CANO generic research draft: correction and safe replacement

Date: 2026-11-07

## Review outcome

The source task `ARAŞTIR BUL ÇALIŞ ÖĞREN GELİŞ` does not name a research subject, population, dataset, or outcome. Its generated plan therefore cannot support domain-specific factual claims. The following items in the old draft are unverified and must be withdrawn, not treated as examples of real evidence: variables A/B/C/D; datasets X/Y/Z and their sizes; the claim of 30+ recent papers; percentages and statistical targets; example DOIs `10.1234/jas.2021.001` and `10.5678/ir.2023.045`; device/software specifications; sample sizes; timelines; and expected results. No literature review, dataset analysis, lab experiment, or field study is recorded as completed.

## Corrected replacement draft

This is a planning template only. It does not assert findings or imply that research has been performed.

1. **Define the question.** Record the research topic, target population or system, intervention/exposure, comparator, primary outcome, time horizon, and constraints. If these are not supplied, stop before making domain-specific claims.
2. **Build an evidence register.** Search primary literature and authoritative datasets only after the question is defined. Record exact title, DOI or stable URL, publication date, source type, retrieval date, and the exact passage supporting each claim. Resolve every DOI and read the source; metadata alone is not evidence. Exclude unresolvable or unrelated references.
3. **Separate evidence from assumptions.** Label each statement as source-supported fact, hypothesis, or unknown. Do not use placeholder variables, invented dataset descriptions, or ungrounded numerical targets as factual content.
4. **Plan analysis after the data are identified.** Define variables, inclusion/exclusion rules, sample size rationale, statistical methods, missing-data handling, and sensitivity checks from the real study design. Do not promise thresholds such as a particular correlation, accuracy, or effect increase before they are justified.
5. **Gate any experiment.** Write a feasible protocol and identify required equipment, funding, permissions, and ethics review. Mark the experiment `not started` until it is actually run; report measured results only with data and reproducible analysis.
6. **Review and release.** Have a qualified domain reviewer inspect the evidence and methods. Preserve a versioned record of sources, data provenance, code, tests, limitations, and unresolved questions. Publish only after the review; keep the draft pending meanwhile.

## BMJ source-specific correction

The official BMJ correction for DOI `10.1136/bmj-2023-075847` says that using baseline standard deviations improved comparability and did **not** materially change the findings. The claim that the correction materially changed findings is contradicted by the correction and should be rejected. The original article reports low CINeMA confidence for walking/jogging and very low confidence for other exercise modalities; do not describe the evidence as high-certainty. The separate DOI `10.64239/pi-tr-qt4802` was not found in the CANO source retrieval and must be excluded unless independently resolved.

Sources:
- https://www.bmj.com/content/384/bmj-2023-075847
- https://www.bmj.com/content/385/bmj.q1024

## State

This correction replaces unsupported specifics with an evidence-gated plan. It does not retroactively change or approve the old CANO mission record, and it does not claim the proposed work has been performed. Keep the mission `review_pending` until an authorized reviewer accepts a scoped, evidence-backed version.
