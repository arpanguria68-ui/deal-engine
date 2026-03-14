---
name: three-statement-model
description: Integrated 3-Statement financial model (Income Statement, Balance Sheet, Cash Flow Statement) for M&A analysis. Use when tasks involve: 3-statement model, three statement, financial model, income statement, revenue projections, balance sheet, cash flow statement, or working capital.
---

# 3-Statement Financial Model — Domain Skill

<correct_patterns>

## Critical Rule: Statements Must Link
The 3 statements are completely interconnected. Any error breaks the model:
```
Income Statement → Net Income → Retained Earnings in Balance Sheet
                              → Starting point of Cash Flow Statement

Balance Sheet: Total Assets = Total Liabilities + Total Equity (MUST ALWAYS BALANCE)

Cash Flow Statement: Ending Cash → Cash & Equivalents on Balance Sheet
```

## Step 1: Income Statement (Top → Down)
```
Revenue
(-) COGS
= Gross Profit        [Gross Margin = Gross Profit / Revenue]
(-) Operating Expenses (SG&A, R&D)
= EBITDA              [EBITDA Margin = EBITDA / Revenue]
(-) D&A
= EBIT
(-) Interest Expense  [based on debt balance × interest rate]
= EBT (Pre-Tax Income)
(-) Income Tax        [Effective Tax Rate × EBT, if EBT > 0]
= Net Income
```

## Step 2: Cash Flow Statement
```
Operating Activities:
  Net Income
  (+) D&A (add back non-cash)
  (±) Changes in Working Capital:
      (+/-) Change in Accounts Receivable
      (+/-) Change in Inventory
      (+/-) Change in Accounts Payable
  = Cash from Operations

Investing Activities:
  (-) Capital Expenditures
  (+) Asset Sale Proceeds (if any)
  = Cash from Investing

Financing Activities:
  (+/-) Debt Issuance / Repayment
  (-) Dividends
  (+) Equity Raised
  = Cash from Financing

Net Change in Cash = Operating + Investing + Financing
Ending Cash = Beginning Cash + Net Change in Cash
```

## Step 3: Balance Sheet Reconciliation
```
Assets:
  Current Assets:
    Cash & Equivalents [links from CFS ending cash]
    Accounts Receivable [Revenue × DSO / 365]
    Inventory [COGS × DIO / 365]
  Long-term Assets:
    PP&E (Prior PP&E + CapEx - D&A)

Liabilities:
  Current Liabilities:
    Accounts Payable [COGS × DPO / 365]
  Long-term Liabilities:
    Long-term Debt [reduced by repayments]

Equity:
  Common Stock + Retained Earnings [prior + Net Income - Dividends]

VERIFY: Total Assets = Total Liabilities + Total Equity
```

## Working Capital Drivers (Must State Explicitly)
| Driver | Typical Range | Industry Benchmark |
|--------|-------------|-------------------|
| DSO (Days Sales Outstanding) | 30-60 days | Cite industry |
| DIO (Days Inventory Outstanding) | 30-90 days | Cite industry |
| DPO (Days Payable Outstanding) | 30-60 days | Cite industry |

</correct_patterns>

<common_mistakes>
- ❌ Balance sheet doesn't balance (A ≠ L+E) — always verify this identity
- ❌ Interest expense not linked to debt balance (must be dynamic)
- ❌ D&A not added back in Cash Flow Statement
- ❌ Tax applied to negative EBT (no tax on losses; create an IF statement)
- ❌ PP&E not rolling forward (PP&E = prior + CapEx - D&A)
- ❌ Working capital changes not showing the correct sign (increase in AR = cash outflow)
- ❌ Cash from CFS doesn't match cash on Balance Sheet
</common_mistakes>
