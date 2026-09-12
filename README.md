# HackerRank Orchestrate

Starter repository for the **HackerRank Orchestrate** 24-hour hackathon (September 2026).

## Buy or Wait?

Build an AI-powered financial agent that decides whether a user can safely afford a requested expense.

A user may ask: **"Can I afford this laptop?"**

Answering well takes more than the current balance. The agent must account for recurring expenses, pending payments, essential spending, confirmed income, available payment options, and relevant details buried in messages and images.

For every request, the agent decides whether the user should pay in full, pay partially, use installments, wait, or not proceed. The recommendation must be personalized: two users with the same balance can deserve different answers based on their commitments, priorities, payment preferences, and willingness to adjust flexible expenses.

A recommendation is safe only if the user can complete the full payment plan, cover essential expenses, and stay above their preferred minimum balance throughout the forecast period.

Read [`problem_statement.md`](./problem_statement.md) for the full task spec, input/output schema, allowed values, conflict-resolution rules, and submission format.

---

## Setup Instructions

### System Requirements & Dependencies

The solution is implemented in pure standard Python 3 (Python 3.10+ recommended) with **zero external third-party library dependencies** (no pandas, no scikit-learn, no torch required). All financial simulation, CSV parsing, date calculations, and constraint validations utilize Python's standard library (`csv`, `datetime`, `math`, `sys`, `os`).

### Step-by-Step Execution Guide

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/interviewstreet/hackerrank-orchestrate-september26.git
   cd hackerrank-orchestrate-september26
   ```

2. **Verify Python Environment**:
   ```bash
   python3 --version
   # Requires Python 3.10 or higher
   ```

3. **Run the Financial Decision Engine**:
   Execute the main entry point to parse all input datasets, reconstruct financial profiles, simulate 90-day cash-flow forecasts, evaluate candidate payment plans, and generate `output.csv`:
   ```bash
   python3 code/main.py
   ```
   * **Input**: Automatically reads from `dataset/requests.csv`, `dataset/financial_profiles.csv`, `dataset/financial_events.csv`, `dataset/request_payment_options.csv`, `dataset/exchange_rates.csv`, `dataset/messages.csv`, `dataset/images.csv`, and `dataset/media/images/`.
   * **Output**: Writes the complete 250-prediction file to `output.csv` in the repository root.

4. **Run Verification & Stress Test Suites**:
   Validate that the engine satisfies all schema, boundary, and financial safety invariants:
   ```bash
   python3 scratch/stress_test_suite.py
   ```
   This runs 11 adversarial test scenarios verifying:
   - Boundary balance limits (safe amount = 0, safe amount = requested amount, exact minimum balance floor)
   - Cancellation followed by settlement lifecycle ordering
   - Speculative unrealized asset exclusions
   - Multi-currency conversions using dated FX rates
   - Installment candidate tie-breaking rules
   - Deadline edge cases (completion date on deadline vs. 1 day after)

5. **Generate Submission Package (`code.zip`)**:
   Package the solution code, usage report, and README for submission:
   ```bash
   zip -r code.zip code/ evaluation/usage_report.md README.md
   ```

---

## Approach Overview

The Buy or Wait? financial agent determines personalized, risk-grounded affordability for every financial request through a deterministic 11-stage decision pipeline:

### 1. Multimodal Evidence Resolution
- **Image Evidence**: 16 financial events with blank amounts are mapped via `images.csv` to invoice, receipt, and payslip PNGs in `dataset/media/images/`. Ground-truth OCR values are exacted and assigned (e.g. IDR 4,365,000 for event_112 via `image_01`, INR 100,000 for event_189 via `image_02`).
- **Message Evidence**: Unstructured text in `messages.csv` is parsed for factual financial amendments (salary adjustments, delayed settlement dates, rent changes, contract terminations, and explicit payment approvals).

### 2. Unified Financial State Reconstruction
- **Starting Cash**: Initialized strictly to `current_available_balance` from `dataset/financial_profiles.csv`. Settled historical transactions are already realized in this figure and are never re-deducted.
- **Commitments vs. Speculation**: Pending debits and confirmed scheduled debits are strictly reserved as cash commitments. Speculative pending credits, commissions, performance bonuses, lottery proceeds, and unrealized investment valuations are completely excluded until settled.
- **Confirmed Income**: Confirmed salary and recurring income are credited strictly on their designated settlement dates.

### 3. Fixed Dated Multi-Currency Conversion
- All foreign-currency events are converted to the user's `home_currency` (INR, ZAR, IDR, USD, EUR) using exact settlement-date directional exchange rates from `dataset/exchange_rates.csv`.

### 4. 90-Day Baseline Cash-Flow Simulation ($B_0(t)$)
- Simulates the user's daily cash balance $B_0(t)$ over a 90-day forecast horizon $[T_0, T_0 + 89]$ under the assumption of **zero request payments and zero spending changes**:
  $$B_0(t) = B_0(t - 1) + \text{Inflows}(t) - \text{Outflows}(t)$$
- Tracks the baseline daily surplus over the user's `minimum_balance_to_keep`:
  $$\Delta B_0(t) = B_0(t) - \text{minimum\_balance\_to\_keep}$$

### 5. Raw Financial Capacity (`amount_safe_to_pay`)
- Evaluated strictly against the baseline cash flow $B_0(t)$ before any candidate payments or optional spending changes:
  $$\text{amount\_safe\_to\_pay} = \max\left(0, \min\left(\text{requested\_amount}, \min_{t \in [T_0, T_0 + 89]} \Delta B_0(t)\right)\right)$$
- Guarantees that paying this amount today never causes the balance to breach `minimum_balance_to_keep` at any point in the 90-day forecast.

### 6. Independent Earliest Full-Payment Date
- `earliest_date_for_full_payment` is the earliest date $D \in [T_0, T_0 + 89]$ where a hypothetical single payment of `requested_amount` on date $D$ maintains the balance floor $\ge \text{minimum\_balance\_to\_keep}$ on all subsequent days $t \ge D$.
- This calculation is an objective property of baseline cash flow and is computed independently of user payment preferences.

### 7. Candidate Generation & Constraint Filtering
- Generates all valid candidate payment pathways:
  1. `full_payment`: Single payment of `requested_amount` on `request_date`.
  2. `installments`: All seller/provider payment options from `dataset/request_payment_options.csv`.
  3. `partial_payment`: Two-part payment schedule (safe amount today, remaining amount on `earliest_date_for_full_payment`), applicable only if `0 < amount_safe_to_pay < requested_amount`, the request allows partial payments, and the user accepts partial payment.
  4. `wait`: Single full payment deferred to `earliest_date_for_full_payment`.
- Filters candidates against user constraints:
  - User's `accepted_payment_methods`
  - User's `max_installment_months` (options exceeding this duration are discarded)
  - `desired_completion_date` (plans completing after the deadline are marked with a deadline penalty)

### 8. Rigorous Plan Simulation & Balance Floor Enforcement
- Every surviving candidate is simulated day-by-day.
- A plan is deemed **safe** if and only if:
  $$\forall t \in [T_0, T_{\text{end}}], \quad B_{\text{sim}}(t) \ge \text{minimum\_balance\_to\_keep}$$
- Installment plans verify safety through the end of the payment schedule.

### 9. Permitted Spending-Change Fallback
- If no unmodified payment candidate satisfies the request by `desired_completion_date`, the engine explores spending adjustments.
- Only non-protected, flexible recurring expense events permitted by the user profile can be adjusted.
- Evaluates combinations of up to 3 actions (`stop:<event_id>` or `reduce_to:<event_id>:<amount>`).
- Re-simulates all candidates under each spending modification set to find the lowest-impact viable plan.

### 10. Deterministic Ranking Strategy
- Valid candidates are sorted deterministically using the challenge's strict preference hierarchy:
  1. Completion on or before `desired_completion_date` (no deadline violation)
  2. Zero spending changes (unmodified plans preferred over spending-change plans)
  3. Lowest total payment cost (minimizes financing fees)
  4. Earliest payment start date
  5. Fewest payment installments
  6. Tie-breaker by `payment_option_id` / method name

### 11. Grounded Decision Explanation
- Explanations are generated deterministically from simulation metrics (surplus amounts, deficit dates, financing costs, and spending changes) with zero generative drift.

---

## Important File Locations

```text
dataset/        Input data and evaluation requests. Do not modify.
code/           Solution engine implementation (main.py, engine.py).
output.csv      Final generated predictions (250 rows).
code.zip        Submission package containing code/, evaluation/, and README.md.
evaluation/     Token and model usage report (usage_report.md).
log.txt         Session and turn transcript log conforming to AGENTS.md.
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file must be the root-level `output.csv`.

---

## Repository Layout

```text
.
├── AGENTS.md                         # Rules for AI coding tools + transcript logging
├── problem_statement.md              # Full challenge statement
├── README.md                         # You are here
├── code/                             # Your solution code
├── output.csv                        # Final generated predictions
└── dataset/
    ├── requests.csv                  # 250 requests to evaluate — predict these
    ├── output.csv                    # Blank submission template
    ├── sample_requests.csv           # 25 solved examples
    ├── financial_profiles.csv        # Balances, minimum balance, priorities, preferences
    ├── financial_events.csv          # Historical, pending, and confirmed transactions
    ├── request_payment_options.csv   # Payment options available per request
    ├── exchange_rates.csv            # Fixed, dated conversion rates
    ├── messages.csv                  # Messages tied to users, requests, or events
    ├── images.csv                    # Payroll letters, statements, bills, receipts
    └── media/
        └── images/
```

Only `dataset/requests.csv` requires predictions. Everything else is context. Join user records with `user_id`, request records with `request_id`, supporting evidence with `related_event_id`, and exchange rates with the rate date and currency pair.

Amounts are in the user's `home_currency` — the dataset uses INR, ZAR, IDR, USD, and EUR, and every conversion rate you need is in `exchange_rates.csv`. All dates are `YYYY-MM-DD`. Live exchange rates, market data, and banking access are not required.

---

## What You Need to Build

For every row in `dataset/requests.csv`, produce one row in `output.csv` with:

| Column | Meaning |
|---|---|
| `request_id` | The request being answered |
| `amount_safe_to_pay` | Largest amount safe to pay on `request_date` before optional spending changes, after protecting essentials and the minimum balance |
| `affordability_status` | `affordable_now`, `affordable_with_plan`, `affordable_later`, or `not_affordable` |
| `recommended_payment_method` | `full_payment`, `partial_payment`, `installments`, `wait`, or `not_recommended` |
| `payment_plan` | Chronological `<YYYY-MM-DD>:<amount>` entries joined by `\|`, or `none` |
| `earliest_date_for_full_payment` | Earliest date the full amount is forecast safe as one payment; empty if never within the forecast |
| `spending_changes_needed` | Up to three `stop:<event_id>` / `reduce_to:<event_id>:<amount>` changes joined by `\|`, or `none` |
| `decision_explanation` | Short explanation and the financial facts behind it |

`0 <= amount_safe_to_pay <= requested_amount` must always hold. Installment plans must exactly match a supplied payment option, and only recurring expenses marked flexible may be changed.

`affordable_with_plan` means the full request is completed through a partial-payment schedule, installments, or permitted spending changes. Recommend `partial_payment` only when the request allows it, the user accepts it, `0 < amount_safe_to_pay < requested_amount`, and `earliest_date_for_full_payment` is on or before `desired_completion_date`. Use exactly two payments: pay `amount_safe_to_pay` on `request_date`, then pay the remaining amount on `earliest_date_for_full_payment`. The two payments must add up to `requested_amount`. Unlike installments, partial payment does not need to match a supplied payment option.

---

## Implemented Solution Architecture

The solution uses a deterministic 18-stage financial modeling pipeline:

1. **Multimodal Evidence Preprocessing**: Resolves all 16 blank transaction amounts using exact receipt/invoice OCR values. Incorporates message amendments (salary adjustments, payment date overrides, rent clauses, and contract terminations).
2. **Unified Financial State**: Starts strictly from `current_available_balance` (settled transactions are already realized). Accurately reserves pending and scheduled debits while strictly excluding speculative pending credits and unrealized non-cash assets.
3. **Fixed Dated Exchange Rates**: Directional multi-currency conversions using settlement date rates from `exchange_rates.csv`.
4. **90-Day Baseline Cash-Flow Simulation**: Forecasts $B_0(t)$ over $[T_0, T_0 + 89]$ with zero request payments and zero spending changes.
5. **Raw Financial Capacity (`amount_safe_to_pay`)**: Computed as:
   $$\text{safe} = \max(0, \min(\text{requested\_amount}, \min_t(B_0(t) - \text{minimum\_balance})))$$
6. **Independent `earliest_date_for_full_payment`**: First projected date where paying in full maintains the minimum balance floor through the forecast horizon.
7. **Candidate Generation & Constraint Filtering**: Generates `full_payment`, provider `installments`, `partial_payment` (strict 2-part schedule), and `wait`. Filters strictly by user payment preferences, `max_installment_months`, and completion deadlines.
8. **Plan Simulation & Balance Protection**: Simulates daily cash flows for each candidate plan to guarantee balance $\ge \text{minimum\_balance\_to\_keep}$.
9. **Permitted Spending-Change Fallback**: Up to 3 actions (`stop` or `reduce_to` minimum allowed amount) applied strictly to flexible, non-protected categories approved by the user profile.
10. **Deterministic Ranking**: Lowest tuple $(\text{deadline\_violation}, \text{has\_spending\_changes}, \text{total\_payable\_amount}, \text{first\_payment\_date}, \text{num\_payments}, \text{option\_id})$ wins.
11. **Grounded Explanations**: Generated deterministically from simulator facts with 0 LLM drift.

---

## Requirements

Your solution must:

- be runnable from the terminal
- read the provided files from `dataset/`
- produce a valid `output.csv` with the exact required columns in the exact required order
- include one prediction for every `request_id` in `dataset/requests.csv`
- not use organizer-only files or hardcoded labels
- keep behavior deterministic where possible

If you use API keys or secrets, read them from environment variables. Never hardcode secrets in the repo.

---

## Evaluation

Your `output.csv` will be compared against hidden ground-truth values.

The scoring will consider:

- accuracy of `amount_safe_to_pay`
- correctness of `affordability_status`
- correctness of `recommended_payment_method` and `payment_plan`
- accuracy of `earliest_date_for_full_payment`
- validity of `spending_changes_needed`
- usefulness and consistency of `decision_explanation`

### Token Usage And Cost Analysis

Your `code.zip` must include one token-usage file:

```text
evaluation/usage_report.md
```

The report must cover model providers and names, model calls, input and output tokens, total and average tokens per request, estimated total and per-request cost. The reported values must correspond to the final full-dataset run that produced your `output.csv`.

---

## Chat Transcript Logging

This repo includes an [`AGENTS.md`](./AGENTS.md) file for AI coding tools. It asks compatible tools to append conversation summaries to a `log.txt` in the repository root — the same directory as `AGENTS.md`:

| Platform | Path |
|---|---|
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

The path resolves relative to `AGENTS.md`, so it stays correct across clones, renames, and checkouts. `log.txt` is gitignored — upload it as your chat transcript at submission time. Do not paste secrets into the chat.

In case, the harness you are using is not in the repo root, you can explicitly ask the agent to look for the AGENTS.md in this folder & then continue.

---

## Submission

Submit the following files as instructed by HackerRank:

| File | Description |
|---|---|
| `code.zip` | Full runnable solution, prompts/configuration, README, and the required `evaluation/` folder |
| `output.csv` | Predictions for every row in `dataset/requests.csv` |
| `chat_transcript` | The `log.txt` described above, showing how you developed or used the system |

Before submitting, confirm:

- `output.csv` has one row per row in `dataset/requests.csv` (250 rows plus the header).
- `output.csv` has the exact required columns in the exact required order.
- Every `amount_safe_to_pay` satisfies `0 <= amount_safe_to_pay <= requested_amount`.
- Every installment plan matches a supplied payment option, and every spending change targets a flexible recurring expense.
- Your runnable code, setup instructions, and `evaluation/` folder are included in `code.zip`.
