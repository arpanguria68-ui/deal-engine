import numpy as np
from app.core.tools.stochastic_engine import StochasticEngine
from app.core.tools.valuation_tools import RunMonteCarloIRRTool


def test_engine():
    print("Testing StochasticEngine...")
    engine = StochasticEngine(n_sim=5000, seed=42)

    # 1. Test CIR non-negativity
    print("Testing CIR Rates non-negativity...")
    cir_paths = engine.simulate_cir(r0=0.03, a=0.2, b=0.04, sigma=0.02, T=5)
    assert np.all(cir_paths >= 0), "CIR produced negative rates!"
    print("CIR Rates: PASSED")

    # 2. Test OU convergence
    print("Testing OU Synergy Fade...")
    ou_paths = engine.ou_synergies(target=20.0, kappa=0.8, theta=10.0, sigma=3.0, T=5)
    mean_terminal = np.mean(ou_paths[:, -1])
    print(f"Mean terminal synergy: {mean_terminal:.2f} (Expected around 10.0)")
    assert 8.0 < mean_terminal < 12.0, "OU paths did not converge near theta."
    print("OU Synergy Fade: PASSED")

    # 3. Test Tool Execution
    print("Testing RunMonteCarloIRRTool...")
    tool = RunMonteCarloIRRTool()
    res = tool.execute(
        entry_ebitda=50.0,
        price=500.0,
        syn_target=15.0,
        kappa=0.5,
        theta_pct=0.5,
        sigma=2.0,
        years=5,
    )
    print(f"Tool execution success: {res.success}")
    if res.success:
        print("Results:\n", res.data)
    else:
        print("Error:", res.error)


if __name__ == "__main__":
    test_engine()
