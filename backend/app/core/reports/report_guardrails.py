from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()

class ReportGuardrails:
    """Validate agent data quality before report generation."""

    @staticmethod
    def validate_agent_results(agent_results: List[Dict]) -> Dict[str, Any]:
        """Check completeness, flag missing critical data."""
        issues = []
        
        agent_types = [r.get("agent_type") for r in agent_results]
        
        if "financial_analyst" not in agent_types:
            issues.append("Missing Critical Data: Financial Analyst results not found. Projections will be unavailable.")
            
        if "risk_assessor" not in agent_types:
            issues.append("Missing Critical Data: Risk Assessor results not found. Risk matrix will be empty.")
            
        # Check confidences are real
        for r in agent_results:
            agent = r.get("agent_type", "unknown")
            conf = r.get("confidence")
            if conf is None or conf == 0.8:  # 0.8 might be the old hardcoded fallback
                logger.warning(f"Suspicious confidence score for {agent}: {conf}")
                
            reasoning = r.get("reasoning", "")
            if len(reasoning) < 50:
                issues.append(f"Quality Warning: {agent} provided exceptionally brief reasoning (< 50 chars).")

        return {"valid": len(issues) == 0, "issues": issues}

    @staticmethod
    def extract_structured_data(agent_results: List[Dict]) -> Dict[str, Any]:
        """Extract and normalize structured data from agent results."""
        extracted = {}
        for r in agent_results:
            agent = r.get("agent_type")
            data = r.get("data", {})
            if not data:
                continue
            extracted[agent] = data
        return extracted

    @staticmethod
    def quality_score(agent_results: List[Dict]) -> float:
        """Compute report quality score (0-1)."""
        if not agent_results:
            return 0.0
            
        # Weights: agent count (30%), confidence avg (40%), reasoning depth (30%)
        agent_score = min(len(agent_results) / 10.0, 1.0) * 0.3
        
        avg_conf = sum(r.get("confidence", 0.5) for r in agent_results) / len(agent_results)
        conf_score = avg_conf * 0.4
        
        avg_len = sum(len(r.get("reasoning", "")) for r in agent_results) / len(agent_results)
        depth_score = min(avg_len / 500.0, 1.0) * 0.3
        
        return round(agent_score + conf_score + depth_score, 2)

    @staticmethod
    def generate_sources_and_uses(financial_data: Dict, target_ev: float) -> Dict[str, Any]:
        """
        Generate a strictly balanced Sources & Uses table.
        This provides a PE-grade Capital Structure layout.
        """
        # Assumptions
        cash_on_sheet = float(financial_data.get("cash", 10.0))
        debt_to_ebitda_mult = 4.0
        ebitda = float(financial_data.get("ebitda", 25.0))
        
        max_debt = ebitda * debt_to_ebitda_mult
        
        uses = {
            "Purchase Equity": target_ev - cash_on_sheet,
            "Refinance Existing Debt": float(financial_data.get("debt", 30.0)),
            "Estimated Fees & Expenses": target_ev * 0.03
        }
        total_uses = sum(uses.values())
        
        term_loan = min(max_debt * 0.6, total_uses * 0.4)
        sub_debt = min(max_debt * 0.4, total_uses * 0.2)
        
        sponsor_equity = total_uses - term_loan - sub_debt
        
        sources = {
            "Term Loan (Senior Debt)": term_loan,
            "Subordinated Notes": sub_debt,
            "Sponsor Equity Contribution": sponsor_equity
        }
        total_sources = sum(sources.values())
        
        return {
            "sources": sources,
            "uses": uses,
            "total_sources": total_sources,
            "total_uses": total_uses,
            "is_balanced": abs(total_sources - total_uses) < 0.01,
            "equity_percentage": sponsor_equity / total_sources
        }
