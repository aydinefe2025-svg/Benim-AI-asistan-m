# LoRA v6 local experiment — 2026-11-10

## Result

The new QLoRA candidate trained successfully but scored below the Ollama base model on the fixed local 18-case keyword smoke suite. The candidate remains inactive.

- Base model: 14/18 (77.8%)
- New candidate: 12/18 (66.7%)
- Training: 24 examples, 2 epochs, Qwen3-8B 4-bit QLoRA; mean training loss 3.5925
- Trainer validation: 23/23 unit tests passed; 24-row dataset accepted by the trainer

## Regressions

Compared with the base model, the candidate regressed on current-fact uncertainty, paid API consent, and independent quality review. It improved on one two-part instruction case. Both models shared failures on training-review consent, tool-completion honesty, and secret-handling checks.

The evaluation is a local keyword-rubric smoke test, not a human or semantic quality judgment. Lower score and the paid-consent regression fail the promotion gate; no model was promoted.

## Data provenance and scope

The experiment used 20 existing assistant-curated repository examples and four assistant-generated examples explicitly authorized for this isolated run. The additions were not user-authored or user-reviewed. No raw chat, credentials, paid APIs, or simulation traces were used. The dataset and adapter weights are not published in this repository.

The previous local experimental adapter service was restored after evaluation. No Render deployment or production model change was made.
