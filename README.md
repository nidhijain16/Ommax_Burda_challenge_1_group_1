# FACTS Topic Opportunity Scout — Executive Cockpit
**TUM × OMMAX AI Hackathon · Hubert Burda Media / FACTS Challenge 1**

An audit-proof, hybrid decision engine combining **deterministic relational scoring** with **Tesseracted Labs Shared AI Gateway** to prioritize new TOP-List topics for Hubert Burda Media, grounded strictly in dataset records with zero hallucination.

---

## Quick Start (Run the Live Prototype)

Run the prototype in a single command:

```bash
# 1. Activate venv & run Streamlit dashboard
.venv/bin/streamlit run app.py
```

The executive cockpit opens automatically in your browser at `http://localhost:8501`.

---

## System Architecture: The Hybrid Model

Our solution uses a **two-layer hybrid architecture**:
1. **Deterministic Relational Engine (Scoring & Governance):**
   - **No LLM touches the scores or status recommendations.**
   - Calculates 5 dimensional scores ($A: 20\%, B: 15\%, C: 25\%, D: 20\%, E: 20\%$) using pure relational queries on the 10 CSV tables.
   - Enforces a strict 9-gate waterfall (*Validate Next*, *Monitor*, *Deprioritise*, *Do Not Pursue*).
   - Guarantees 100% auditability, sub-50ms execution, and zero pass/fail gate disqualifications.
2. **Executive AI Analyst Copilot (Tesseracted Labs Shared AI Gateway):**
   - Connected to the hackathon's shared gateway endpoint:
     `https://tesseracted.com/access_83444ac6-49d6-467b-a61f-0d39a98f0e87/ai_gateway/v1`
   - Supported models:
     - `deepseek-ai/DeepSeek-V4.1-Flash` (Default: ultra-fast, sharp reasoning)
     - `moonshotai/Kimi-K3.1-Pro` (Long-context German/English synthesis)
     - `zai-org/GLM-5.3-Flash`
   - **Two Core AI Jobs:**
     - **✨ One-Click Executive Investment Memo:** Synthesizes a C-level investment pitch strictly grounded in the card's verified record IDs.
     - **💬 Live Jury Q&A Copilot:** Answers real-time questions from OMMAX consultants or Burda executives about risks, white space, and status rationale.

---

## Key Features

1. **Deterministic Relational Ingestion:** Ingests all 10 CSV tables, builds relational dossiers, and counts unique publishers from `08_sources.csv` to satisfy Golden Rule #3.
2. **Zero Hallucination Guarantee:** Enforces Pydantic schema validation on all record IDs (`[F...]`, `[S...]`, `[I...]`, `[C...]`, `[P...]`, `[R...]`, `[L...]`, `[SRC...]`).
3. **Transparent Status Recommendations:** Outputs *Validate Next*, *Monitor*, *Deprioritise*, or *Do Not Pursue* with explicit rationale.
4. **Human-in-the-Loop Governance:** Automatically flags high-liability YMYL topics, BGH court precedents (`02_learnings.csv`), and vulnerable consumer groups.
5. **Interactive Executive Cockpit (Streamlit):**
   - KPI metrics bar across all 32 taxonomy sectors.
   - 6-dimension score breakdown & market landscape classification.
   - Full 14-field Opportunity Cards with rich status badges and risk alerts.
   - Live Jury Query box to assess unexpected wildcard topics on the fly.
   - Tesseracted AI Gateway integration for instant memo generation and live Q&A.
   - 1-click downloads for `cards.json`, `cards.md`, and `LOGIC.md`.

---

## Optional Step: Wedge Title Creator (default OFF)

For each card, DeepSeek V4 Pro (via the Tesseracted Labs gateway) proposes up to 3 narrower TOP-list "wedge" titles (one entity type + one decision moment, optional region); `src/wedges.py` validates them in code.
```bash
cd "Challenge 1: FACTS Topic Opportunity Scout"
export FACTS_GATEWAY_API_KEY=...            # required; optional: FACTS_GATEWAY_BASE_URL
export FACTS_WEDGE_MODEL=tesseracted-labs-gmbh/deepseek-ai/DeepSeek-V4-Pro-0813   # default model id
python generate_deliverables.py --wedges    # without --wedges the output is unchanged
python -m unittest discover -s tests        # offline tests, LLM mocked
```
- Wedges are **hypotheses**: never scored; card status and score are untouched. Shown as `wedges` (+ `parent_title`) in `cards.json` and a "Narrower wedges (hypotheses, unscored)" section in `cards.md`.
- Rejected (with reasons in `wedge_validation_report.json`): unknown record IDs or IDs not in the card's evidence, title not narrower than the parent or > 12 words, numbers not found in a cited record, superlatives, market-size/population claims. Portfolio near-duplicates are flagged, not rejected. Each wedge carries `size_status: "unvalidated"` and `generated_by`.
- No key, no `openai` package, HTTP error, empty or truncated reply → no wedges; the pipeline still runs.

### Optional: Wedge Validity Score (`--wedge-scores`, requires `--wedges`, default OFF)

An independent model, Kimi K3.1 Pro, judges each valid wedge on 5 criteria (0–4 each): evidence support, entity grounding, specificity, decision clarity and distinctiveness. Python then computes `validity.score` (0–100, weighted; unknown criteria are dropped, never counted as 0; 2 or more unknown → `unscored`). Kimi's own overall number is ignored.
```bash
export FACTS_SCORE_MODEL=tesseracted-labs-gmbh/moonshotai/Kimi-K3.1-Pro   # default; same gateway env vars as above
python generate_deliverables.py --wedges --wedge-scores
```
- **What it is:** a model-assessed plausibility check (`basis: "llm_assessed"`), shown next to deterministic `data_checks` (IDs exist and are in the card, entity named in a cited record, no sibling duplicate). Labels: high ≥ 75, medium 50–74, low < 50. `low`/`unscored` → `needs_human_review`.
- **What it is not:** data-validated or market-sized. It only re-orders the wedges within a card. Card status, score and ranking are unchanged, and wedges stay `size_status: "unvalidated"`. Reasons citing unknown IDs or numbers are discarded. Failures leave the wedge `unscored` and are logged under `scoring` in `wedge_validation_report.json`.

---

## Deliverables Generated

- 📄 **[cards.json](Challenge%201%3A%20FACTS%20Topic%20Opportunity%20Scout/cards.json)** — Machine-readable opportunity cards.
- 📑 **[cards.md](Challenge%201%3A%20FACTS%20Topic%20Opportunity%20Scout/cards.md)** — Executive opportunity cards report.
- 📐 **[LOGIC.md](Challenge%201%3A%20FACTS%20Topic%20Opportunity%20Scout/LOGIC.md)** — One-page prioritisation methodology & scoring rubric.
- 🗺️ **TEAM_EXECUTION_PLAN.md** — Team strategy & 5-minute pitch script (kept outside the repository).
