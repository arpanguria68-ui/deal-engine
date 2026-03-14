---
name: dcf-model
description: Institutional-quality DCF (Discounted Cash Flow) model creation for private equity and investment banking deal analysis. Follows Wall Street formatting standards. Use when tasks involve: DCF valuation, WACC calculation, terminal value, equity bridge, intrinsic value, or free cash flow projections.
---

# DCF Model — Domain Skill

## Critical Constraints (Read First)

<correct_patterns>

### Step 1: Data Collection & Validation
- Collect 3-5 years of historical financials (Revenue, EBITDA, EBIT, Net Income, D&A, CapEx, Working Capital).
- **Validate Net Debt vs Net Cash**: Net Debt = Total Debt - Cash. If negative, it's a Net Cash position.
- Confirm diluted shares outstanding (include options, RSUs, convertibles).
- Cross-check revenue growth rates against industry benchmarks.
- Verify tax rate: typically 21-28% for US companies.

### Step 2: Revenue Projections (5-Year Explicit Period)
- Start from LTM (Last Twelve Months) actuals.
- Apply Bear/Base/Bull scenario growth rates:
  - **Bear**: Conservative (e.g., 5-8%)
  - **Base**: Most likely (e.g., 10-14%)
  - **Bull**: Optimistic (e.g., 15-20%)
- Year 1-2: Near-term visibility growth
- Year 3-5: Gradual moderation toward industry average

### Step 3: Build FCF in Proper Sequence
```
EBIT
(-) Taxes (EBIT × Effective Tax Rate)
= NOPAT (Net Operating Profit After Tax)
(+) D&A (non-cash; % of revenue, typically 3-6%)
(-) CapEx (% of revenue, typically 4-8%)
(-) Δ Working Capital (% of revenue change)
= Unlevered Free Cash Flow (UFCF)
```

### Step 4: WACC Calculation (CAPM)
```
Cost of Equity = Rf + β × ERP
  where: Rf = 10Y Treasury Yield, ERP = 5.0-6.0%

Cost of Debt (after-tax) = Pre-Tax Yield × (1 - Tax Rate)

Capital Structure:
  Equity Weight = Market Cap / (Market Cap + Net Debt)
  Debt Weight = Net Debt / (Market Cap + Net Debt)

WACC = (Ke × We) + (Kd × Wd)
```
Typical WACC Ranges: Large Cap Stable 7-9%, Growth 9-12%, High-risk 12-15%.

### Step 5: Discount Cash Flows (Mid-Year Convention)
- Period 1 = 0.5, Period 2 = 1.5, etc.
- Discount Factor = 1 / (1 + WACC)^Period

### Step 6: Terminal Value
Preferred: Perpetuity Growth Method
```
TV = Final Year FCF × (1 + g) / (WACC - g)
```
**Constraint**: Terminal growth (g) MUST be < WACC. Maximum: 3.5% for high-growth, 2.5% for mature.
TV sanity check: Should be 50-70% of Enterprise Value.

### Step 7: Enterprise-to-Equity Bridge
```
(+) PV of Projected FCFs
(+) PV of Terminal Value
= Enterprise Value (EV)
(-) Net Debt [or + Net Cash]
(-) Minority Interests
(+) Non-operating Assets
= Equity Value
÷ Diluted Shares Outstanding
= Implied Price Per Share
```

### Step 8: Sensitivity Analysis (MANDATORY)
Produce three 5×5 sensitivity tables:
1. **WACC vs Terminal Growth Rate** → Implied EV/Share
2. **Revenue Growth vs EBIT Margin** → Implied EV/Share
3. **Entry Multiple vs Exit Multiple** → IRR/MOIC

Each cell must independently recalculate the full DCF for that parameter combination.

</correct_patterns>

<common_mistakes>

- ❌ Terminal growth > WACC (creates infinite or negative value)
- ❌ Operating expenses as % of Gross Profit instead of Revenue
- ❌ Missing mid-year convention on discount periods
- ❌ Using book value instead of market value for capital structure weights
- ❌ Terminal value representing more than 80% of Enterprise Value
- ❌ Sensitivity tables with only 1 variable (always use 2D matrix)
- ❌ Tax rate applied to EV bridge (should apply to EBIT → NOPAT)
- ❌ Forgetting to subtract minority interests from equity bridge
- ❌ Sensitivity tables with approximations instead of full recalculations

</common_mistakes>

## Output Format

Deliver your DCF analysis with this structure:

### 1. Historical Summary Table
| Metric | FY-2 | FY-1 | LTM |
|--------|------|------|-----|
| Revenue | $X | $X | $X |
| EBIT Margin | X% | X% | X% |
| FCF Margin | X% | X% | X% |
| ROIC | X% | X% | X% |

### 2. Valuation Bridge
| Component | Value ($M) |
|-----------|-----------|
| PV FCFs (5Y) | $X |
| PV Terminal Value | $X |
| Enterprise Value | $X |
| (-) Net Debt | ($X) |
| Equity Value | $X |
| Implied Per Share | $X.XX |

### 3. Scenario Summary
| Scenario | WACC | g | Implied EV | Per Share |
|----------|------|---|-----------|---------|
| Bear | X% | X% | $X | $X |
| Base | X% | X% | $X | $X |
| Bull | X% | X% | $X | $X |
