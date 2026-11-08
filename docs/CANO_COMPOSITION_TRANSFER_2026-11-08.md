# CANO — Previously unrewarded compositional task C, three 30-seed partitions

**Topic:** `organism.digital`; GitHub #413. **Research-scoped four-locus simulation only.** This does not alter the existing three-locus `digital_vm` or the live daily-calendar data. Does not perform AI model training, biology, physical robotic replication, or autonomous network propagation.

## Mechanism and prospective acceptance

Previous 3-locus protected-core experiments gave 4/30 and 5/30 positive seeds but did not pass the robustness gate; not directly comparable to this NEW four-locus design. Founder `(COPY_REST, TASK_A, NOP, DIVIDE)` allows both A and B instructions to appear in a *viable copying program*. Training 120 ticks with A reward for 40 ticks and B reward thereafter. Never reward task C in training. New synthetic *compositional C task* is `TASK_A AND TASK_B` in a viable genome. No new C opcode; this tests a **previously unrewarded combination of previously seen task instructions**, not transfer to an arbitrary external unseen task.

Five arms: original unrestricted, structural core-only protected, structural + **task grammar** (middle alleles only NOP/A/B), no mutation, no division. All arms get the same *source* RNG proposals and seed sequence where applicable; rejected illegal candidate alleles revert to parent, not directed to B. This modifies **accepted** mutation rates; it is engineered, not evolutionarily learned. Resource 1 per tick, capacity 48, mutation rate 0.08, B/A task reward 2.

After training: copy each state, freeze mutation, reset all existing individual energy values to 3, and perform 20 steps of composition-only C reward 2 and separately a zero-reward null. The energy reset was introduced after a **failing behavioral test** detected inherited training-energy saturation: under the original holdout both reward and null had full capacity, so it was not an informative fitness comparison. The initial saturated-holdout exploratory outputs were **discarded and are not represented as confirmatory evidence**. The original two seed series (0..29, 100..129) had been inspected before the reset; treat them as exploratory. A distinct 200..229 cohort was run after the holdout method and acceptance gate were fixed, but it is an in-session check, not external scientific preregistration.

The predeclared strict per-cohort gate is: at least 50% of **all** seeds have positive grammar-vs-core C-carrier share difference, exact one-sided sign p<0.05 excluding ties, normal-approx 95% mean gain lower>0, normal-approx 95% holdout population gain lower>=0, and all controls pass. **Full acceptance requires all three independent seed groups to pass without altering thresholds.**

## Actual measured results

| Seeds | C-share positive /30 | Exact sign p | Mean paired C-share gain [approx 95% CI] | C-only holdout population mean diff [approx 95% CI] | Strict per-partition gate |
|---|---|---|---|---|---|
| 0..29 | 19/30 (9 ties; 2 negatives) | 0.0001106262 | +0.03958 [+0.02293, +0.05624] | +0.0000 [+0.0000, +0.0000] | **PASS** |
| 100..129 | 20/30 (8 ties; 2 negatives) | 6.055832e-05 | +0.07083 [+0.01397, +0.12770] | +1.5667 [-1.5040, +4.6373] | **FAIL** |
| 200..229 | 19/30 (10 ties; 1 negatives) | 2.002716e-05 | +0.05764 [+0.00054, +0.11474] | +2.0667 [-0.7478, +4.8811] | **FAIL** |

**All three partitions together:** 450 finite simulated experiments; 57/90 positive grammar-vs-core task-C share comparisons, 5 negative, 28 ties. All five arms, source genotype cap and independent genotype/negative controls were checked on each set. Note that individual *positivity* cannot substitute for the predeclared population holdout rule; **full robust/transfer acceptance FAILED**, because two independent partitions' lower confidence bounds of C-only holdout population differences were negative. In the first partition the holdout comparison was exactly tied (CI [0,0]) despite better C-carrier fraction, so a strict increase in holdout population is *not* proven.

**Important:** Novel task C uses an engineer-designed reward function, and some organisms contain both A and B because of mutation, not generalized reasoning. In controls lacking mutation or division, all task-C carrier births and no-division births behave as expected. Reporting only the positive sign tests would be misleading. No claim of broadly robust adaptation, general reasoning, self-training or biological evolution.

## Verification and provenance

- New implementation: `organism_lab_cloud/organism_lab/compositional_transfer_study.py`, test: `organism_lab_cloud/organism_lab/tests/test_compositional_transfer_study.py`. Existing `digital_vm.py` Git blob SHA **`0ced308713956ebd43fa58ef29bb31502101d001`** remains unchanged.
- Eight local Python 3.13 tests passed, including an observed **RED → GREEN** holdout-energy saturation test and tamper/replay rejection. Canonical GitHub Actions must rerun them on Python 3.11/3.12 with the actual existing VM.
- Signed-*by-digest*, NOT cryptographically signed, JSON stores complete per-seed/arm traces of end-of-training and holdout metrics. Immutable unique filenames and idempotent write behavior. The verifier recomputes each report independently using the same deterministic code; altered report data or forged digest are rejected.
- New workflow `.github/workflows/cano-compositional-transfer.yml` runs test + independent replay + file SHA checks. No production Render deploy, secrets or network actuators.
- Main Notion Organism Lab research page: https://app.notion.com/p/40d2bd61682a81ee8745c28af627d98b. Canonical issue: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413.

## Open questions

1. Why does improving functional composite genotype fraction not reliably improve short-term holdout population versus core-only control? Is resource/population saturation limiting selection of the score?
2. Replicate under distinct **predeclared** resource/pressure ranges, with matched holdout initialization and no post-hoc threshold fitting, including more realistic memory and task semantics.
3. Independent external evaluator and actual agent performance benchmark required before any self-improving-agent claim. Leave #413 open.