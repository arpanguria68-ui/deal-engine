"""Deal Scoring Engine"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class RiskLevel(Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScoreComponent:
    """Individual scoring component"""
    name: str
    score: float  # 0-1
    weight: float
    confidence: float
    reasoning: str
    factors: List[str]


@dataclass
class DealScoreResult:
    """Complete deal scoring result"""
    total_score: float  # 0-100
    confidence: float
    risk_level: RiskLevel
    components: List[ScoreComponent]
    recommendations: List[str]
    red_flags: List[str]
    green_flags: List[str]


class DealScorer:
    """Multi-factor deal scoring engine"""
    
    # Default weights for scoring components
    DEFAULT_WEIGHTS = {
        "market": 0.20,
        "team": 0.15,
        "traction": 0.20,
        "financials": 0.20,
        "risk": 0.15,
        "strategic_fit": 0.10
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.logger = structlog.get_logger()
    
    def score(
        self,
        market_data: Dict[str, Any],
        team_data: Dict[str, Any],
        traction_data: Dict[str, Any],
        financial_data: Dict[str, Any],
        risk_data: Dict[str, Any],
        strategic_data: Dict[str, Any]
    ) -> DealScoreResult:
        """
        Calculate comprehensive deal score
        
        Args:
            market_data: Market opportunity data
            team_data: Team quality data
            traction_data: Business traction metrics
            financial_data: Financial performance data
            risk_data: Risk assessment data
            strategic_data: Strategic fit data
            
        Returns:
            DealScoreResult with complete scoring breakdown
        """
        components = []
        
        # Score each component
        market_component = self._score_market(market_data)
        components.append(market_component)
        
        team_component = self._score_team(team_data)
        components.append(team_component)
        
        traction_component = self._score_traction(traction_data)
        components.append(traction_component)
        
        financial_component = self._score_financials(financial_data)
        components.append(financial_component)
        
        risk_component = self._score_risk(risk_data)
        components.append(risk_component)
        
        strategic_component = self._score_strategic_fit(strategic_data)
        components.append(strategic_component)
        
        # Calculate weighted total
        total_score = sum(
            comp.score * self.weights.get(comp.name, 0) * 100
            for comp in components
        )
        
        # Calculate confidence
        confidence = sum(comp.confidence for comp in components) / len(components)
        
        # Determine risk level
        risk_level = self._determine_risk_level(total_score, risk_component.score)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(components)
        
        # Identify flags
        red_flags = self._identify_red_flags(components)
        green_flags = self._identify_green_flags(components)
        
        self.logger.info(
            "Deal scored",
            total_score=total_score,
            risk_level=risk_level.value,
            confidence=confidence
        )
        
        return DealScoreResult(
            total_score=round(total_score, 2),
            confidence=round(confidence, 2),
            risk_level=risk_level,
            components=components,
            recommendations=recommendations,
            red_flags=red_flags,
            green_flags=green_flags
        )
    
    def _score_market(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score market opportunity"""
        factors = []
        score = 0.5
        confidence = 0.7
        
        # Market size
        tam = data.get("total_addressable_market", 0)
        if tam > 10000000000:  # $10B+
            score += 0.2
            factors.append("Large TAM ($10B+)")
        elif tam > 1000000000:  # $1B+
            score += 0.1
            factors.append("Significant TAM ($1B+)")
        
        # Growth rate
        growth_rate = data.get("market_growth_rate", 0)
        if growth_rate > 0.2:
            score += 0.15
            factors.append("High market growth (>20%)")
        elif growth_rate > 0.1:
            score += 0.08
            factors.append("Moderate market growth")
        
        # Competition
        competition_level = data.get("competition_level", "medium")
        if competition_level == "low":
            score += 0.1
            factors.append("Favorable competitive landscape")
        elif competition_level == "high":
            score -= 0.1
            factors.append("Highly competitive market")
        
        # Entry barriers
        if data.get("high_entry_barriers", False):
            score += 0.05
            factors.append("Protective entry barriers")
        
        return ScoreComponent(
            name="market",
            score=max(0, min(1, score)),
            weight=self.weights["market"],
            confidence=confidence,
            reasoning=f"Market opportunity scored based on TAM of ${tam:,.0f} and {growth_rate:.1%} growth",
            factors=factors
        )
    
    def _score_team(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score team quality"""
        factors = []
        score = 0.5
        confidence = 0.6
        
        # Founder experience
        founder_experience = data.get("founder_experience_years", 0)
        if founder_experience > 10:
            score += 0.2
            factors.append("Experienced founders (10+ years)")
        elif founder_experience > 5:
            score += 0.1
            factors.append("Moderately experienced founders")
        
        # Previous exits
        if data.get("previous_exits", 0) > 0:
            score += 0.15
            factors.append(f"Previous exits: {data['previous_exits']}")
        
        # Team completeness
        if data.get("team_complete", False):
            score += 0.1
            factors.append("Complete leadership team")
        
        # Domain expertise
        if data.get("domain_expertise", False):
            score += 0.1
            factors.append("Strong domain expertise")
        
        # Employee retention
        retention = data.get("employee_retention", 0)
        if retention > 0.85:
            score += 0.1
            factors.append("High employee retention")
        
        return ScoreComponent(
            name="team",
            score=max(0, min(1, score)),
            weight=self.weights["team"],
            confidence=confidence,
            reasoning=f"Team scored based on {founder_experience} years founder experience",
            factors=factors
        )
    
    def _score_traction(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score business traction"""
        factors = []
        score = 0.5
        confidence = 0.75
        
        # Revenue growth
        revenue_growth = data.get("revenue_growth", 0)
        if revenue_growth > 1.0:
            score += 0.2
            factors.append("Hypergrowth (>100% YoY)")
        elif revenue_growth > 0.5:
            score += 0.15
            factors.append("Strong growth (>50% YoY)")
        elif revenue_growth > 0.2:
            score += 0.08
            factors.append("Moderate growth")
        
        # Customer metrics
        customer_growth = data.get("customer_growth", 0)
        if customer_growth > 0.5:
            score += 0.1
            factors.append("Strong customer acquisition")
        
        # Retention
        retention = data.get("customer_retention", 0)
        if retention > 0.9:
            score += 0.15
            factors.append("Excellent retention (>90%)")
        elif retention > 0.8:
            score += 0.08
            factors.append("Good retention")
        
        # Unit economics
        if data.get("positive_unit_economics", False):
            score += 0.1
            factors.append("Positive unit economics")
        
        # Partnerships
        if data.get("strategic_partnerships", []):
            score += 0.05
            factors.append("Strategic partnerships in place")
        
        return ScoreComponent(
            name="traction",
            score=max(0, min(1, score)),
            weight=self.weights["traction"],
            confidence=confidence,
            reasoning=f"Traction scored with {revenue_growth:.1%} revenue growth",
            factors=factors
        )
    
    def _score_financials(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score financial performance"""
        factors = []
        score = 0.5
        confidence = 0.8
        
        # Revenue
        revenue = data.get("annual_revenue", 0)
        if revenue > 10000000:  # $10M+
            score += 0.15
            factors.append("Strong revenue ($10M+)")
        elif revenue > 1000000:  # $1M+
            score += 0.1
            factors.append("Significant revenue ($1M+)")
        
        # Margins
        gross_margin = data.get("gross_margin", 0)
        if gross_margin > 0.7:
            score += 0.15
            factors.append("High gross margins (>70%)")
        elif gross_margin > 0.5:
            score += 0.1
            factors.append("Healthy gross margins")
        
        # Path to profitability
        if data.get("path_to_profitability", False):
            score += 0.1
            factors.append("Clear path to profitability")
        
        # Cash position
        cash_months = data.get("cash_runway_months", 0)
        if cash_months > 18:
            score += 0.1
            factors.append("Strong cash position (18+ months)")
        elif cash_months > 12:
            score += 0.05
            factors.append("Adequate cash runway")
        
        # Burn rate
        burn_rate = data.get("monthly_burn_rate", 0)
        if burn_rate < revenue * 0.3:  # Low burn relative to revenue
            score += 0.1
            factors.append("Efficient capital usage")
        
        return ScoreComponent(
            name="financials",
            score=max(0, min(1, score)),
            weight=self.weights["financials"],
            confidence=confidence,
            reasoning=f"Financials scored with ${revenue:,.0f} revenue and {gross_margin:.1%} margins",
            factors=factors
        )
    
    def _score_risk(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score risk factors (inverse - higher score = lower risk)"""
        factors = []
        score = 0.5
        confidence = 0.65
        
        # Legal risks
        legal_risks = data.get("legal_risks", [])
        if not legal_risks:
            score += 0.15
            factors.append("No significant legal risks")
        else:
            score -= len(legal_risks) * 0.05
            factors.append(f"{len(legal_risks)} legal risks identified")
        
        # Regulatory risks
        regulatory_risks = data.get("regulatory_risks", [])
        if not regulatory_risks:
            score += 0.1
            factors.append("Minimal regulatory exposure")
        else:
            score -= len(regulatory_risks) * 0.05
        
        # Market risks
        market_risks = data.get("market_risks", [])
        score -= len(market_risks) * 0.03
        
        # Dependency risks
        if data.get("customer_concentration", 0) > 0.3:
            score -= 0.1
            factors.append("High customer concentration risk")
        
        if data.get("key_person_dependency", False):
            score -= 0.1
            factors.append("Key person dependency")
        
        # Mitigation
        if data.get("risk_mitigation_plan", False):
            score += 0.1
            factors.append("Risk mitigation plans in place")
        
        return ScoreComponent(
            name="risk",
            score=max(0, min(1, score)),
            weight=self.weights["risk"],
            confidence=confidence,
            reasoning=f"Risk scored with {len(legal_risks)} legal and {len(regulatory_risks)} regulatory risks",
            factors=factors
        )
    
    def _score_strategic_fit(self, data: Dict[str, Any]) -> ScoreComponent:
        """Score strategic fit"""
        factors = []
        score = 0.5
        confidence = 0.6
        
        # Synergies
        synergies = data.get("identified_synergies", [])
        if synergies:
            score += min(len(synergies) * 0.05, 0.2)
            factors.append(f"{len(synergies)} synergies identified")
        
        # Strategic alignment
        if data.get("strategic_alignment", False):
            score += 0.15
            factors.append("Strong strategic alignment")
        
        # Cultural fit
        if data.get("cultural_fit_assessment", "neutral") == "good":
            score += 0.1
            factors.append("Good cultural fit")
        
        # Integration complexity
        complexity = data.get("integration_complexity", "medium")
        if complexity == "low":
            score += 0.1
            factors.append("Low integration complexity")
        elif complexity == "high":
            score -= 0.1
            factors.append("High integration complexity")
        
        return ScoreComponent(
            name="strategic_fit",
            score=max(0, min(1, score)),
            weight=self.weights["strategic_fit"],
            confidence=confidence,
            reasoning=f"Strategic fit scored with {len(synergies)} identified synergies",
            factors=factors
        )
    
    def _determine_risk_level(self, total_score: float, risk_score: float) -> RiskLevel:
        """Determine overall risk level"""
        if total_score > 75 and risk_score > 0.7:
            return RiskLevel.LOW
        elif total_score > 50 and risk_score > 0.5:
            return RiskLevel.MODERATE
        elif total_score > 30:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
    
    def _generate_recommendations(self, components: List[ScoreComponent]) -> List[str]:
        """Generate investment recommendations"""
        recommendations = []
        
        # Find lowest scoring components
        sorted_components = sorted(components, key=lambda c: c.score)
        
        for comp in sorted_components[:2]:
            if comp.score < 0.5:
                recommendations.append(
                    f"Address {comp.name} concerns: {comp.reasoning}"
                )
        
        # Add positive recommendations
        high_scoring = [c for c in components if c.score > 0.75]
        if high_scoring:
            recommendations.append(
                f"Leverage strengths in: {', '.join(c.name for c in high_scoring)}"
            )
        
        return recommendations
    
    def _identify_red_flags(self, components: List[ScoreComponent]) -> List[str]:
        """Identify red flags"""
        flags = []
        
        for comp in components:
            if comp.score < 0.3:
                flags.append(f"Critical concern in {comp.name}")
            for factor in comp.factors:
                if any(word in factor.lower() for word in ["risk", "concern", "issue", "problem"]):
                    flags.append(f"{comp.name}: {factor}")
        
        return flags
    
    def _identify_green_flags(self, components: List[ScoreComponent]) -> List[str]:
        """Identify positive indicators"""
        flags = []
        
        for comp in components:
            if comp.score > 0.8:
                flags.append(f"Strong {comp.name} profile")
            for factor in comp.factors:
                if any(word in factor.lower() for word in ["excellent", "strong", "large", "high", "good"]):
                    flags.append(f"{comp.name}: {factor}")
        
        return flags


def risk_label(score: float) -> str:
    """Convert score to risk label"""
    if score > 75:
        return "Low Risk"
    elif score > 50:
        return "Moderate Risk"
    elif score > 30:
        return "High Risk"
    return "Critical Risk"
