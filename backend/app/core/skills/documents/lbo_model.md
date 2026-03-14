---
name: lbo-model
description: Institutional LBO (Leveraged Buyout) modeling for private equity deal evaluation. Use when tasks involve: LBO analysis, leveraged buyout, IRR, MOIC, equity returns, debt waterfall, exit multiples, or PE deal structuring.
---

# LBO Model — Domain Skill

<correct_patterns>

### Key LBO Concepts
- **Entry**: Acquire company at Entry EV = EBITDA × Entry Multiple
- **Financing**: Split between Equity (30-40%) and Debt (60-70%)
- **Exit**: After 3-7 year hold, sell at Exit EV = EBITDA × Exit Multiple

### Step 1: Entry Capitalization
```
Entry EV = LTM EBITDA × Entry Multiple
Sources:
  Sponsor Equity = Entry EV × Equity %   (typically 30-40%)
  Senior Secured Debt = Entry EV × X%     (e.g., 3.0-4.0x EBITDA)
  Subordinated Debt = Entry EV × X%       (e.g., 1.0-2.0x EBITDA)
  
Debt / EBITDA (Leverage Ratio): Typically 4.0-6.0x for healthy businesses
```

### Step 2: Debt Amortization Schedule
- Senior Debt: Mandatory 5-10% annual amortization + excess cash flow sweep
- Subordinated: PIK or bullet maturity; no mandatory amortization
- Model cash flow sweep: After debt service, free cash repays senior debt first

### Step 3: Free Cash Flow for Debt Repayment
```
EBITDA × (1 - Tax Rate)    [simplified; use NOPAT ideally]
(-) CapEx
(-) Change in Working Capital
(-) Mandatory Debt Service
= FCF available for optional sweep
```

### Step 4: Exit Proceeds Waterfall
```
Exit EV = Exit Year EBITDA × Exit Multiple
(-) Remaining Senior Debt
(-) Remaining Subordinated Debt
(-) Transaction Fees (1-2% of Exit EV)
= Equity Proceeds to Sponsor
```

### Step 5: Returns Calculation
```
IRR: Solve for r in: Equity Investment = Equity Proceeds / (1+r)^Hold Period
MOIC: Equity Proceeds / Equity Investment
```
Return thresholds:
- Excellent: IRR > 25%, MOIC > 3.0x
- Good: IRR 20-25%, MOIC 2.5-3.0x
- Acceptable: IRR 15-20%, MOIC 2.0-2.5x
- Poor: IRR < 15%, MOIC < 2.0x

### Step 6: Sensitivity Tables (MANDATORY)
Produce at minimum:
1. **Entry Multiple vs Exit Multiple** → IRR and MOIC
2. **EBITDA Margin vs Revenue Growth** → IRR at base exit multiple
</correct_patterns>

<common_mistakes>
- ❌ Forgetting to model mandatory debt amortization each year
- ❌ Using EBITDA as FCF (EBITDA ≠ FCF; subtract taxes, CapEx, WC, debt service)
- ❌ No excess cash flow sweep mechanic (reduces debt faster in good years)
- ❌ IRR calculated using equity investment as Year 0 only — must include add-on equity injections
- ❌ Leverage ratio above 6.5x without credit quality justification
- ❌ Exit multiple significantly above entry multiple without market reason
- ❌ Circular reference in PIK interest without proper resolution
</common_mistakes>

## LBO Output Table Structure
| Metric | Bear | Base | Bull |
|--------|------|------|------|
| Entry EV ($M) | $X | $X | $X |
| Leverage (x) | X.Xx | X.Xx | X.Xx |
| Exit EV ($M) | $X | $X | $X |
| Equity Proceeds ($M) | $X | $X | $X |
| IRR | X% | X% | X% |
| MOIC | X.Xx | X.Xx | X.Xx |
