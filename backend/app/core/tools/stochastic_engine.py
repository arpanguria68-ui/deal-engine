"""
Stochastic Simulation Engine for DealForge AI.

Advanced M&A modeling tools introducing:
- Ornstein-Uhlenbeck (OU) process for mean-reverting synergy fading.
- Vasicek & CIR models for stochastic discount rate generation.
- Full Monte Carlo IRR to replace static point estimates.
"""

import numpy as np
from scipy.optimize import minimize
from typing import Dict, Any, Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)


class StochasticEngine:
    """Core mathematical engine for stochastic finance simulations."""

    def __init__(self, n_sim: int = 10000, seed: int = 42):
        self.n_sim = n_sim
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def ou_synergies(
        self,
        target: float,
        kappa: float,
        theta: float,
        sigma: float,
        T: float,
        dt: float = 1 / 12,
    ) -> np.ndarray:
        """
        Produce paths for Ornstein-Uhlenbeck (OU) synergy fade.

        Args:
            target: Initial synergy target level (at t=0).
            kappa: Reversion speed (fade velocity).
            theta: Long-term sustainable mean.
            sigma: Volatility (execution risk).
            T: Total years to simulate.
            dt: Time step size (default: 1 month).

        Returns:
            np.ndarray of shape (n_sim, int(T/dt)+1) representing synergy paths over time.
        """
        N_steps = int(T / dt)
        paths = np.zeros((self.n_sim, N_steps + 1))
        paths[:, 0] = target

        # Exact conditional distribution for OU process
        decay = np.exp(-kappa * dt)
        var_exact = (sigma**2 / (2 * kappa)) * (1 - np.exp(-2 * kappa * dt))
        std_exact = np.sqrt(var_exact)

        for t in range(1, N_steps + 1):
            Z = self.rng.standard_normal(self.n_sim)
            paths[:, t] = theta + (paths[:, t - 1] - theta) * decay + std_exact * Z

        return paths

    def simulate_vasicek(
        self, r0: float, a: float, b: float, sigma: float, T: float, dt: float = 1 / 12
    ) -> np.ndarray:
        """
        Simulate short-term rates using the Vasicek model (allows negative rates).

        Args:
            r0: Initial short rate.
            a: Speed of mean reversion.
            b: Long-term mean level.
            sigma: Volatility.

        Returns:
            np.ndarray of shape (n_sim, N_steps+1)
        """
        N_steps = int(T / dt)
        paths = np.zeros((self.n_sim, N_steps + 1))
        paths[:, 0] = r0

        # Exact conditional distribution for Vasicek (similar to OU)
        decay = np.exp(-a * dt)
        var_exact = (sigma**2 / (2 * a)) * (1 - np.exp(-2 * a * dt))
        std_exact = np.sqrt(var_exact)

        for t in range(1, N_steps + 1):
            Z = self.rng.standard_normal(self.n_sim)
            paths[:, t] = b + (paths[:, t - 1] - b) * decay + std_exact * Z

        return paths

    def simulate_cir(
        self, r0: float, a: float, b: float, sigma: float, T: float, dt: float = 1 / 12
    ) -> np.ndarray:
        """
        Simulate short-term rates using the CIR model (strictly positive rates if 2ab > sigma^2).
        Uses Euler-Maruyama with full truncation (reflection) boundary.
        """
        N_steps = int(T / dt)
        paths = np.zeros((self.n_sim, N_steps + 1))
        paths[:, 0] = r0

        for t in range(1, N_steps + 1):
            Z = self.rng.standard_normal(self.n_sim)
            # Full truncation strategy to prevent negative square roots
            r_prev_plus = np.maximum(paths[:, t - 1], 0)
            dr = (
                a * (b - r_prev_plus) * dt
                + sigma * np.sqrt(r_prev_plus) * np.sqrt(dt) * Z
            )
            paths[:, t] = paths[:, t - 1] + dr

            # Additional safety: force non-negative entirely
            paths[:, t] = np.maximum(paths[:, t], 1e-6)

        return paths

    def run_irr_monte_carlo(
        self,
        entry_ebitda: float,
        price: float,
        syn_target: float,
        kappa: float = 0.5,
        theta_pct: float = 0.5,
        sigma: float = 2.0,
        T: int = 5,
    ) -> Dict[str, Any]:
        """
        Run a full Monte Carlo simulation to compute expected IRR distribution
        accounting for stochastic synergy fading.

        Assumes simplified baseline 5-year FCF model where FCF = EBITDA - fixed_costs,
        plus the dynamic synergies over time, evaluated against the purchase price.

        Args:
            entry_ebitda: Target's base EBITDA (annual).
            price: Upfront purchase price.
            syn_target: Target synergies in year 0.
            kappa: OU speed of fade.
            theta_pct: Long-term sustainable synergies as a % of syn_target.
            sigma: Volatility of synergy realization.

        Returns:
            Dictionary containing statistical metrics (mean, p10, p90, etc.)
        """
        # Step 1: Generate synergy paths (monthly step for precision)
        dt = 1 / 12
        N_steps = int(T / dt)
        theta_abs = syn_target * theta_pct

        syn_paths = self.ou_synergies(
            target=syn_target, kappa=kappa, theta=theta_abs, sigma=sigma, T=T, dt=dt
        )

        # Step 2: Aggregate monthly synergies to annual
        annual_synergies = np.zeros((self.n_sim, T))
        for y in range(T):
            start_m = y * 12 + 1
            end_m = (y + 1) * 12 + 1
            # Average monthly run-rate annualized
            annual_synergies[:, y] = np.mean(syn_paths[:, start_m:end_m], axis=1)

        # Step 3: Compute total FCF paths
        # Baseline FCF assumed to be ~60% of EBITDA conversion for simplicity
        base_fcf = entry_ebitda * 0.60
        fcf_paths = base_fcf + annual_synergies

        # Step 4: Terminal Value (Year 5) - simple 10x EBITDA multiple on terminal EBITDA
        terminal_ebitda = entry_ebitda + annual_synergies[:, -1]
        terminal_value = terminal_ebitda * 10
        fcf_paths[:, -1] += terminal_value

        # Step 5: Compute IRR for each path
        # numpy financial is obsolete; using a basic bisect mapping or root finder is heavy for 10k sims.
        # We will compute NPV for a range of discount rates and find the root.
        irrs = np.zeros(self.n_sim)

        # Using a vectorized approximation for IRR
        # Generate cashflow arrays: CF0 = -price
        cfs = np.hstack((np.full((self.n_sim, 1), -price), fcf_paths))

        # Since standard np.irr is deprecated and slow on matrices, we compute
        # approximate IRR using standard root finding approximation for regular 5-year cash flows.
        # Average cashflow per year
        for i in range(self.n_sim):
            try:
                # Use a fast internal IRR function
                irrs[i] = _np_irr_fallback(cfs[i, :])
            except:
                irrs[i] = 0.0  # Fallback if no root

        # Filter valid IRRs (-100% to 500%)
        valid_irrs = irrs[(irrs > -1.0) & (irrs < 5.0)]

        if len(valid_irrs) == 0:
            valid_irrs = np.array([0.0])

        return {
            "mean_irr": float(np.mean(valid_irrs)),
            "median_irr": float(np.median(valid_irrs)),
            "p10_irr": float(np.percentile(valid_irrs, 10)),
            "p90_irr": float(np.percentile(valid_irrs, 90)),
            "prob_above_15pct": float(np.mean(valid_irrs > 0.15)),
            "std_dev_irr": float(np.std(valid_irrs)),
        }

    # ─── Vasicek MLE Calibration ───────────────────────────────────

    @staticmethod
    def _vasicek_neg_loglik(params: np.ndarray, r: np.ndarray, dt: float) -> float:
        """
        Negative log-likelihood of the Vasicek model (to be minimized).

        Uses the exact conditional Gaussian transition density:
            r(t+dt) | r(t) ~ N(theta + (r(t) - theta)*exp(-kappa*dt),
                                (sigma^2 / 2*kappa) * (1 - exp(-2*kappa*dt)))
        """
        kappa, theta, sigma = params

        if kappa < 1e-8 or sigma < 1e-8:
            return 1e12

        a = np.exp(-kappa * dt)
        b = theta * (1 - a)
        c2 = (sigma**2 / (2 * kappa)) * (1 - a**2)

        if c2 <= 0:
            return 1e12

        residuals = r[1:] - (b + a * r[:-1])
        n = len(residuals)
        ll = -0.5 * n * np.log(2 * np.pi * c2) - 0.5 * np.sum(residuals**2 / c2)

        return -ll

    def calibrate_vasicek_mle(
        self,
        r: np.ndarray,
        dt: float = 1 / 252,
        initial_guess: Optional[List[float]] = None,
        bounds: Optional[List[tuple]] = None,
        method: str = "L-BFGS-B",
    ) -> Dict[str, Any]:
        """
        Calibrate Vasicek model parameters (kappa, theta, sigma) via exact MLE.

        Based on the conditional Gaussian log-likelihood of the OU process.
        Uses OLS-based initial guess → L-BFGS-B optimization.

        Args:
            r: 1D array of observed short rates (daily frequency recommended).
            dt: Time step in years (1/252 for daily, 1/12 for monthly).
            initial_guess: [kappa, theta, sigma] — optional starting values.
            bounds: [(min_k, max_k), (min_t, max_t), (min_s, max_s)].
            method: Scipy optimization method.

        Returns:
            Dict with fitted params, log-likelihood, standard errors, half-life.
        """
        r = np.asarray(r, dtype=float)
        if len(r) < 30:
            raise ValueError("Need at least ~30 observations for reliable calibration")

        # OLS-based initial guess if not provided
        if initial_guess is None:
            dr = np.diff(r)
            r_lag = r[:-1]
            slope, intercept = np.polyfit(r_lag, dr, 1)
            kappa_ols = max(0.01, -slope / dt)
            theta_ols = intercept / slope if slope != 0 else float(np.mean(r))
            sigma_ols = float(np.std(dr - (intercept + slope * r_lag)) / np.sqrt(dt))
            initial_guess = [kappa_ols, theta_ols, sigma_ols]

        # Default bounds
        if bounds is None:
            bounds = [
                (1e-5, 10.0),
                (float(min(r)) * 0.5, float(max(r)) * 1.5),
                (1e-5, 0.1),
            ]

        # Run optimization
        res = minimize(
            self._vasicek_neg_loglik,
            x0=initial_guess,
            args=(r, dt),
            method=method,
            bounds=bounds,
            options={"disp": False, "maxiter": 1000},
        )

        if not res.success:
            logger.warning(
                "Vasicek MLE optimizer did not converge — results may be unstable"
            )

        kappa, theta, sigma = res.x
        loglik = -res.fun

        # Approximate standard errors from inverse Hessian
        try:
            hess_inv = res.hess_inv.todense()
            se = np.sqrt(np.diag(hess_inv))
        except Exception:
            se = [float("nan")] * 3

        half_life = np.log(2) / kappa if kappa > 1e-8 else float("inf")

        return {
            "kappa": float(kappa),
            "theta": float(theta),
            "sigma": float(sigma),
            "log_likelihood": float(loglik),
            "kappa_se": float(se[0]),
            "theta_se": float(se[1]),
            "sigma_se": float(se[2]),
            "half_life_years": float(half_life),
            "n_observations": len(r),
            "dt_years": dt,
            "success": bool(res.success),
            "message": str(res.message),
        }

    def simulate_vasicek_paths(
        self,
        r0: float,
        kappa: float,
        theta: float,
        sigma: float,
        T: float = 5.0,
        dt: float = 1 / 252,
        n_paths: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Simulate multiple Vasicek short-rate paths using fitted parameters.

        Convenience wrapper around simulate_vasicek for calibration output.

        Args:
            r0: Initial short rate.
            kappa: Speed of mean reversion (= 'a' in simulate_vasicek).
            theta: Long-term mean level (= 'b' in simulate_vasicek).
            sigma: Volatility.
            T: Simulation horizon in years.
            dt: Time step.
            n_paths: Number of paths (defaults to self.n_sim).

        Returns:
            Dict with 'time_grid', 'paths', and 'mean_path'.
        """
        if n_paths and n_paths != self.n_sim:
            # Temporarily override n_sim
            orig_n_sim = self.n_sim
            self.n_sim = n_paths
            paths = self.simulate_vasicek(r0, a=kappa, b=theta, sigma=sigma, T=T, dt=dt)
            self.n_sim = orig_n_sim
        else:
            paths = self.simulate_vasicek(r0, a=kappa, b=theta, sigma=sigma, T=T, dt=dt)

        n_steps = paths.shape[1]
        time_grid = np.linspace(0, T, n_steps).tolist()

        # Analytical mean path: E[r(t)] = theta + (r0 - theta) * exp(-kappa * t)
        t_arr = np.linspace(0, T, n_steps)
        mean_path = theta + (r0 - theta) * np.exp(-kappa * t_arr)

        return {
            "time_grid": time_grid,
            "paths": paths.tolist(),
            "mean_path": mean_path.tolist(),
            "n_paths": paths.shape[0],
        }


def _np_irr_fallback(values: np.ndarray) -> float:
    """Internal fast IRR using np.roots."""
    # The NPV formula implies finding roots of polynomial: sum( c_t * x^(T-t) ) = 0, where x = 1/(1+r)
    # Using numpy's roots:
    res = np.roots(values[::-1])
    # Find the real roots > 0
    mask = (res.imag == 0) & (res.real > 0)
    real_roots = res.real[mask]
    if len(real_roots) == 0:
        return 0.0

    # x = 1/(1+r) => r = 1/x - 1
    rates = 1.0 / real_roots - 1.0

    # Return the rate closest to zero (typical convention)
    idx = np.argmin(np.abs(rates))
    return rates[idx]
