# Implementation PRD: DealForge AI (Sentient Swarm Edition)

## 1. Executive Summary
DealForge AI is a multi-agent M&A simulation workspace designed to replicate the rigorous analytical workflows of top-tier consulting firms (e.g., McKinsey). The project is moving from a mock-data prototype to a production-ready system that enforces structural integrity through **MECE Issue Trees**, **Deterministic Math (Pyodide)**, and **Adversarial Red-Teaming**.

## 2. Core Vision & Soul
The "Soul" of DealForge AI is defined by three pillars:
*   **Structural Soul**: Every analysis starts with a hypothesis and a MECE (Mutually Exclusive, Collectively Exhaustive) issue tree.
*   **Mathematical Soul**: 0% arithmetic error tolerance. All financial logic is executed in sandboxed Python code, not LLM text generation.
*   **Adversarial Soul**: A dedicated Red Team agent hunts for "Strategic Silences" and historical M&A deal-breakers.

---

## 3. Technical Alignment & Codebase Refactoring

### A. Reasoning Framework (Refactoring `BaseAgent`)
**Current State**: Agents perform linear data summarization using simple tool calling.
**Target State**:
*   **Hypothesis-First Initiation**: `BaseAgent.run()` must be refactored to generate an `IssueTree` (branching logic) before attempting retrieval or modeling.
*   **MECE Verification**: An internal `Orchestrator` node will verify if the generated sub-branches are collectively exhaustive.

### B. Mathematical Integrity (Refactoring `ArchitectAgent`)
**Current State**: Python modeling exists but lacks circular reference handling and audit-ready Excel binding.
**Target State**:
*   **Pyodide Sandbox**: Execute all `financial_analyst` logic in a WebAssembly sandbox to guarantee deterministic outputs.
*   **Excel Formula DNA**: Use `xlwings` to inject active formulas (e.g., `=MIN(Balance, Cash*Sweep%)`) into templates rather than flat values.
*   **Stub Period Handling**: Implement mid-year convention discounting as the default projection logic.

### C. Qualitative Validation (Implementing `HaluGate`)
**Current State**: Basic confidence scores.
**Target State**:
*   **NLI Classification Layer**: Implement a Natural Language Inference layer to classify every qualitative claim as *Entailment* (supported), *Neutral* (flagged), or *Contradiction* (blocked).
*   **Non-GAAP Excision**: Specifically hunt for aggressive add-backs in MD&A and earnings call transcripts.

---

## 4. Key Workflows

### 4.1 GP-Led Continuation Vehicle (CV) Simulation
1.  **Librarian Agent**: Ingests LPA and Bid Spread data room; normalizes to `financial_payload.json`.
2.  **Strategist Agent**: Branches into MECE nodes (Price Fairness, Economic Parity, Governance Integrity).
3.  **Architect Agent**: Solves circular debt waterfalls iteratively in Python.
4.  **Editor Agent**: Renders Mermaid Sankey diagrams and renders audit citations for every cell.

### 4.2 Liability Management (LMT) stressed borrower simulation
*   **Loophole Detection**: Librarian scans credit agreements for "Drop-downs," "Double dips," and "Up-tiers."
*   **Recovery Modeling**: Architect runs Monte Carlo iterations (10,000 baseline with standard error convergence check).

---

## 5. Development Roadmap (4-Week Sprint)

| Week | Focus | Codebase Milestone |
| :--- | :--- | :--- |
| **Week 1** | **Ingestion & Invariants** | Refactor `Librarian` with open-source OCR (`pdfminer`) and layout parsing. Establish "Unit of Account" rules. |
| **Week 2** | **Structural Reasoning** | Refactor `BaseAgent` with `IssueTree` logic. Implement MECE branch generation for Antitrust/Tech CDD. |
| **Week 3** | **Quantitative Rigor** | Finalize `Architect` circularity solver and `.xlsx` formula-linked output binding via `xlwings`. |
| **Week 4** | **Human-in-the-Loop** | Deploy the **Escalation Kill-Switch** UI. Finalize **HaluGate** Severity 4 blocking logic. |

---

## 6. Implementation Checklist for Team Delegation
- [ ] **Task 1: The Formula Library**: Port ARO, DTA/DTL, and NWC algebraic reduction formulas into the `Architect` Python module.
- [ ] **Task 2: Definition Drift**: Build a semantic reconciliation tool in the `Librarian` agent to detect if EBITDA definitions mismatch between the Credit and Purchase agreements.
- [ ] **Task 3: Strategic Silence Detector**: Create a Red Team heuristic that flags branches of an issue tree that have "No Data Found" despite management claiming completeness.
- [ ] **Task 4: The Heartbeat**: Implement a WebSocket shared state where the Tax Agent's "Reverse Morris Trust" trigger forces an immediate IRR re-computation in the Architect's dashboard view.

---

**Vision Summary**: DealForge AI is no longer an "AI Assistant"—it is a **Verified Deal Simulator** that produces auditable, McKinsey-grade artifacts on an open-source budget.
