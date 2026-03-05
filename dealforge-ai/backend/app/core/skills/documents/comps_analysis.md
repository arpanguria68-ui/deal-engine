---
name: comps-analysis
description: Comparable Companies (Trading Comps) and Precedent Transactions analysis for M&A deal valuation. Use when tasks involve: comps, comparable companies, trading multiples, EV/EBITDA, EV/Revenue, P/E, precedent transactions, or peer analysis.
---

# Comparable Companies & Precedent Transactions — Domain Skill

<correct_patterns>

## Trading Comps — Step-by-Step Process

### Step 1: Identify Comparable Companies
Criteria for a valid comparable (must match at least 3 of 4):
- **Same industry** (2-3 digit GICS code)
- **Similar size** (Revenue within 0.5x–2.0x of target)
- **Similar growth profile** (Revenue CAGR within ±5%)
- **Similar business model** (recurring vs. transactional, product vs. services)

List 5-8 comparables. Name each, ticker, and state the matching criteria.

### Step 2: Collect LTM Financials for Each Comparable
Required metrics for each comparable:
- Enterprise Value (Current Market Cap + Net Debt)
- Revenue (LTM)
- EBITDA (LTM), EBITDA Margin
- Net Income (LTM)
- Revenue Growth (1-year)
- Gross Margin

### Step 3: Calculate Trading Multiples
| Multiple | Formula |
|---------|---------|
| EV/Revenue | EV ÷ LTM Revenue |
| EV/EBITDA | EV ÷ LTM EBITDA |
| EV/EBIT | EV ÷ LTM EBIT |
| P/E | Share Price ÷ EPS |
| EV/Gross Profit | EV ÷ Gross Profit (for SaaS/tech) |

### Step 4: Calculate Summary Statistics
For each multiple, report: **Min, 25th Percentile, Median, 75th Percentile, Max**
Use Median and 25th-75th percentile range as the primary reference range.

### Step 5: Apply to Target Company
```
Target EV (Low) = Target Metric × 25th Pct Multiple
Target EV (Mid) = Target Metric × Median Multiple
Target EV (High) = Target Metric × 75th Pct Multiple
```
Always show implied values for BOTH EV/EBITDA and EV/Revenue.

### Step 6: Precedent Transactions (if requested)
- Use M&A deals in the same sector from last 3-5 years
- Control premium typically 20-30% above public trading comps
- Precedent multiples typically higher than trading comps (liquidity premium)

## Output Format
| Company | EV ($M) | Revenue | EV/Rev | EBITDA | EV/EBITDA | NTM Growth |
|---------|---------|---------|--------|--------|-----------|------------|
| Comp A | $X | $X | Xx | $X | Xx | X% |
| **Summary Statistics** | | | | | | |
| Median | — | — | Xx | — | Xx | — |
| 25th Pct | — | — | Xx | — | Xx | — |
| 75th Pct | — | — | Xx | — | Xx | — |

</correct_patterns>

<common_mistakes>
- ❌ Using only 1-2 comps (always use 5-8 for statistical validity)
- ❌ Mixing LTM vs NTM multiples in the same table without labelling
- ❌ Including companies with very different business models (e.g., mixing SaaS with hardware)
- ❌ Not adding control premium when comparing trading comps to M&A precedents
- ❌ Applying multiples to EBITDA but ignoring negative EBITDA cases (use EV/Revenue instead)
- ❌ Reporting only the median; always show 25th/75th percentile range
</common_mistakes>
