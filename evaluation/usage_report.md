# Usage Report: Buy or Wait? Financial Decision Agent

## Model Providers & Models Used
- **OCR Engine**: Tesseract OCR (Local, deterministic extraction of structured receipts and invoices)
- **Primary Logic**: Purely Deterministic Cash-Flow Engine (Python 3)
- **Explanation Generator**: Grounded Deterministic Template Engine (with zero LLM drift)

## Summary of Final Full-Dataset Run
- **Total Requests Evaluated**: 250 requests
- **Total Model / OCR Calls**: 16 image OCR calls (100% resolved)
- **LLM Decisions**: 0 calls (Decision policy is 100% deterministic per competition contract)
- **Input Tokens**: 0 tokens
- **Output Tokens**: 0 tokens
- **Average Tokens per Request**: 0.0 tokens
- **Total Cost**: $0.00
- **Cost per Request**: $0.00

## Resource Breakdown
| Component | Engine / Tool | Calls | In Tokens | Out Tokens | Cost ($) |
|---|---|---|---|---|---|
| Multimodal OCR | Tesseract 5.5 | 16 | N/A | N/A | $0.00 |
| Financial Simulation | Deterministic Core | 250 | 0 | 0 | $0.00 |
| Candidate Ranking | Deterministic Comparator | 250 | 0 | 0 | $0.00 |
| Explanation Synthesis | Rule-Grounded Generator | 250 | 0 | 0 | $0.00 |
| **Total** | | **266** | **0** | **0** | **$0.00** |
