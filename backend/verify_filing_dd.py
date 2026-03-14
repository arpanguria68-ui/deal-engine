"""Quick verification script for Vasicek MLE and Filing DD tool."""

import sys

sys.path.insert(0, ".")

# Test 1: Vasicek MLE Calibration
print("=" * 60)
print("TEST 1: Vasicek MLE Calibration")
print("=" * 60)
from app.core.tools.stochastic_engine import StochasticEngine
import numpy as np

engine = StochasticEngine(n_sim=1, seed=42)
paths = engine.simulate_vasicek(
    r0=0.045, a=0.45, b=0.035, sigma=0.012, T=5.0, dt=1 / 252
)
result = engine.calibrate_vasicek_mle(paths[0], dt=1 / 252)

print(
    f"Fitted: kappa={result['kappa']:.3f}, theta={result['theta']:.4f}, sigma={result['sigma']:.4f}"
)
print(f"True:   kappa=0.450, theta=0.0350, sigma=0.0120")
print(f"Success: {result['success']}")
print(f"Half-life: {result['half_life_years']:.2f} years")
print(f"Log-likelihood: {result['log_likelihood']:.2f}")
print()

# Test 2: simulate_vasicek_paths
print("TEST 2: simulate_vasicek_paths")
sim_result = engine.simulate_vasicek_paths(
    r0=0.045,
    kappa=result["kappa"],
    theta=result["theta"],
    sigma=result["sigma"],
    T=2.0,
    dt=1 / 12,
    n_paths=5,
)
print(f"Paths generated: {sim_result['n_paths']}")
print(f"Time grid length: {len(sim_result['time_grid'])}")
print()

# Test 3: Filing Due Diligence Engine
print("=" * 60)
print("TEST 3: Filing Due Diligence Engine")
print("=" * 60)
from app.core.tools.filing_due_diligence import FilingDueDiligenceEngine, detect_region

dd_engine = FilingDueDiligenceEngine()

# Feature extraction
text1 = "The company continues strong growth in core markets with improved revenue performance."
text2 = "Due to macroeconomic pressures and litigation risks, we are implementing cost controls and restructuring."

features1 = dd_engine.compute_filing_features(text1)
features2 = dd_engine.compute_filing_features(text2)
print(f"Text 1 features: {features1}")
print(f"Text 2 features: {features2}")
print()

# Filing comparison
comparison = dd_engine.compare_filing_texts(
    text1, text2, section_name="mda", form_type="10-K", region="US"
)
print(f"Similarity: {comparison['similarity']:.4f}")
print(f"Flags: {comparison['flags']}")
print(f"Is abnormal: {comparison['is_abnormal']}")
print()

# Financial impact prediction
impact = dd_engine.predict_financial_impact([comparison])
print(f"Predicted ROA shift: {impact['avg_roa_shift']:.4f}")
print(f"High impact count: {impact['high_impact_count']}")
print()

# Region detection
print(f"MSFT -> {detect_region('MSFT')}")
print(f"RELIANCE.NS -> {detect_region('RELIANCE.NS')}")
print(f"SAP.DE -> {detect_region('SAP.DE')}")
print()

# 8-K Event clustering
events = [
    {
        "filed_at": "2025-01-10",
        "text": "Quarterly earnings results exceeded expectations",
    },
    {
        "filed_at": "2025-01-12",
        "text": "Merger agreement with TechCorp for acquisition",
    },
    {"filed_at": "2025-01-15", "text": "New director appointed following acquisition"},
    {"filed_at": "2025-06-01", "text": "Annual revenue forecast updated"},
]
clusters = dd_engine.cluster_8k_events(events, max_days_gap=30)
print(f"Event clusters found: {len(clusters)}")
for c in clusters:
    print(
        f"  Cluster {c['cluster_id']}: {c['event_types']} ({c['filing_count']} filings, high_risk={c['high_risk']})"
    )
print()

# Test 4: Tool registration
print("=" * 60)
print("TEST 4: Tool Router Registration")
print("=" * 60)
from app.core.tools.filing_due_diligence import FilingDueDiligenceTool

tool = FilingDueDiligenceTool()
print(f"Tool name: {tool.name}")
print(f"Tool description: {tool.description[:80]}...")
print(f"Engine initialized: {tool.engine is not None}")
print()

print("ALL TESTS PASSED!")
