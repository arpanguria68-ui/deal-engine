"""Reflection Engine for Agent Self-Evaluation"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class ReflectionGrade(Enum):
    EXCELLENT = "excellent"  # 0.9 - 1.0
    GOOD = "good"            # 0.7 - 0.89
    ACCEPTABLE = "acceptable" # 0.5 - 0.69
    POOR = "poor"            # 0.3 - 0.49
    FAILED = "failed"        # 0.0 - 0.29


@dataclass
class ReflectionResult:
    """Result of reflection evaluation"""
    score: float  # 0.0 - 1.0
    grade: ReflectionGrade
    feedback: str
    improvements: List[str]
    confidence: float


class ReflectionEngine:
    """Evaluates agent outputs and provides feedback"""
    
    def __init__(self):
        self.evaluation_criteria = {
            "completeness": 0.25,
            "accuracy": 0.30,
            "reasoning_quality": 0.25,
            "actionability": 0.20
        }
    
    def evaluate(
        self,
        task: str,
        agent_output: Dict[str, Any],
        expected_format: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> ReflectionResult:
        """
        Evaluate agent output quality
        
        Args:
            task: Original task description
            agent_output: The agent's output
            expected_format: Expected output structure
            context: Additional context for evaluation
            
        Returns:
            ReflectionResult with score and feedback
        """
        scores = {}
        
        # Completeness check
        scores["completeness"] = self._check_completeness(agent_output, expected_format)
        
        # Accuracy check (basic heuristics)
        scores["accuracy"] = self._check_accuracy(agent_output)
        
        # Reasoning quality
        scores["reasoning_quality"] = self._check_reasoning(agent_output)
        
        # Actionability
        scores["actionability"] = self._check_actionability(agent_output)
        
        # Calculate weighted score
        total_score = sum(
            scores[criterion] * weight 
            for criterion, weight in self.evaluation_criteria.items()
        )
        
        # Determine grade
        grade = self._score_to_grade(total_score)
        
        # Generate feedback
        feedback = self._generate_feedback(scores, agent_output)
        
        # Suggest improvements
        improvements = self._suggest_improvements(scores)
        
        logger.info(
            "Reflection evaluation complete",
            score=total_score,
            grade=grade.value,
            task_preview=task[:50]
        )
        
        return ReflectionResult(
            score=total_score,
            grade=grade,
            feedback=feedback,
            improvements=improvements,
            confidence=self._calculate_confidence(scores)
        )
    
    def _check_completeness(
        self, 
        output: Dict[str, Any], 
        expected_format: Optional[Dict]
    ) -> float:
        """Check if output has all expected fields"""
        if not expected_format:
            return 0.8  # Default if no format specified
        
        expected_keys = set(expected_format.get("required", []))
        actual_keys = set(output.keys())
        
        if not expected_keys:
            return 0.8
        
        matched = len(expected_keys & actual_keys)
        return matched / len(expected_keys)
    
    def _check_accuracy(self, output: Dict[str, Any]) -> float:
        """Check output for accuracy indicators"""
        score = 1.0
        
        output_str = str(output).lower()
        
        # Penalize uncertainty markers
        uncertainty_markers = ["i think", "maybe", "possibly", "uncertain", "unclear"]
        for marker in uncertainty_markers:
            if marker in output_str:
                score -= 0.1
        
        # Penalize errors
        if "error" in output_str or "failed" in output_str:
            score -= 0.3
        
        # Reward specific numbers and data
        if any(char.isdigit() for char in output_str):
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _check_reasoning(self, output: Dict[str, Any]) -> float:
        """Check quality of reasoning"""
        score = 0.5
        
        output_str = str(output).lower()
        
        # Look for reasoning indicators
        reasoning_markers = [
            "because", "therefore", "thus", "as a result",
            "analysis", "reasoning", "conclusion", "based on"
        ]
        
        for marker in reasoning_markers:
            if marker in output_str:
                score += 0.1
        
        # Check for structured reasoning
        if "reasoning" in output or "analysis" in output:
            score += 0.2
        
        return min(1.0, score)
    
    def _check_actionability(self, output: Dict[str, Any]) -> float:
        """Check if output is actionable"""
        score = 0.5
        
        output_str = str(output).lower()
        
        # Look for actionable indicators
        action_markers = [
            "recommend", "should", "next step", "action",
            "implement", "proceed", "consider"
        ]
        
        for marker in action_markers:
            if marker in output_str:
                score += 0.1
        
        # Check for specific recommendations
        if "recommendations" in output or "next_steps" in output:
            score += 0.2
        
        return min(1.0, score)
    
    def _score_to_grade(self, score: float) -> ReflectionGrade:
        """Convert numeric score to grade"""
        if score >= 0.9:
            return ReflectionGrade.EXCELLENT
        elif score >= 0.7:
            return ReflectionGrade.GOOD
        elif score >= 0.5:
            return ReflectionGrade.ACCEPTABLE
        elif score >= 0.3:
            return ReflectionGrade.POOR
        else:
            return ReflectionGrade.FAILED
    
    def _generate_feedback(self, scores: Dict[str, float], output: Dict) -> str:
        """Generate human-readable feedback"""
        feedback_parts = []
        
        if scores["completeness"] < 0.7:
            feedback_parts.append("Output is incomplete. Missing expected fields.")
        
        if scores["accuracy"] < 0.7:
            feedback_parts.append("Accuracy concerns detected. Review data and assumptions.")
        
        if scores["reasoning_quality"] < 0.6:
            feedback_parts.append("Reasoning could be more explicit. Show your work.")
        
        if scores["actionability"] < 0.6:
            feedback_parts.append("Output lacks clear actionable recommendations.")
        
        if not feedback_parts:
            feedback_parts.append("Good quality output with clear reasoning and actionable insights.")
        
        return " ".join(feedback_parts)
    
    def _suggest_improvements(self, scores: Dict[str, float]) -> List[str]:
        """Suggest specific improvements"""
        suggestions = []
        
        if scores["completeness"] < 0.8:
            suggestions.append("Include all required output fields")
        
        if scores["accuracy"] < 0.8:
            suggestions.append("Verify data sources and calculations")
        
        if scores["reasoning_quality"] < 0.7:
            suggestions.append("Provide explicit reasoning steps")
        
        if scores["actionability"] < 0.7:
            suggestions.append("Add specific, actionable recommendations")
        
        return suggestions
    
    def _calculate_confidence(self, scores: Dict[str, float]) -> float:
        """Calculate overall confidence in the evaluation"""
        values = list(scores.values())
        if not values:
            return 0.5
        
        # Lower variance = higher confidence
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        
        confidence = 1.0 - min(variance * 2, 0.5)
        return confidence


class RewardEngine:
    """Calculates rewards for RL optimization"""
    
    def __init__(self):
        self.weights = {
            "reflection": 0.4,
            "user_feedback": 0.3,
            "task_completion": 0.2,
            "efficiency": 0.1
        }
    
    def compute_reward(
        self,
        reflection_score: float,
        user_feedback: float = 0.5,
        task_completed: bool = True,
        iterations_used: int = 1,
        max_iterations: int = 10
    ) -> float:
        """
        Compute composite reward score
        
        Args:
            reflection_score: Score from reflection engine (0-1)
            user_feedback: User rating (0-1)
            task_completed: Whether task was completed
            iterations_used: Number of iterations used
            max_iterations: Maximum allowed iterations
            
        Returns:
            Composite reward score (0-1)
        """
        # Task completion bonus
        completion_score = 1.0 if task_completed else 0.0
        
        # Efficiency score (fewer iterations = better)
        efficiency = 1.0 - (iterations_used / max_iterations)
        
        # Weighted combination
        reward = (
            self.weights["reflection"] * reflection_score +
            self.weights["user_feedback"] * user_feedback +
            self.weights["task_completion"] * completion_score +
            self.weights["efficiency"] * efficiency
        )
        
        logger.info(
            "Reward computed",
            reward=reward,
            reflection=reflection_score,
            user_feedback=user_feedback
        )
        
        return reward


class RLOptimizer:
    """Reinforcement Learning optimizer for agent prompts"""
    
    def __init__(self):
        self.prompt_adjustments = []
        self.performance_history = []
    
    def adjust_prompt(self, reward: float, current_prompt: str) -> str:
        """
        Adjust prompt based on reward signal
        
        Args:
            reward: Computed reward (0-1)
            current_prompt: Current agent prompt
            
        Returns:
            Adjusted prompt
        """
        adjustments = []
        
        if reward < 0.3:
            adjustments.append("\n\nCRITICAL: Provide detailed step-by-step reasoning.")
            adjustments.append("Verify all facts and cite sources explicitly.")
        elif reward < 0.5:
            adjustments.append("\n\nIMPORTANT: Show your reasoning process clearly.")
            adjustments.append("Double-check calculations and assumptions.")
        elif reward < 0.7:
            adjustments.append("\n\nNOTE: Be more specific in your recommendations.")
        
        # Track adjustment
        self.prompt_adjustments.append({
            "reward": reward,
            "adjustments": adjustments
        })
        
        adjusted_prompt = current_prompt + "".join(adjustments)
        
        logger.info("Prompt adjusted based on reward", reward=reward)
        
        return adjusted_prompt
    
    def get_strategy_recommendation(self, reward_history: List[float]) -> str:
        """Get strategy recommendation based on reward history"""
        if len(reward_history) < 3:
            return "Continue current strategy. Collect more data."
        
        recent_avg = sum(reward_history[-3:]) / 3
        overall_avg = sum(reward_history) / len(reward_history)
        
        if recent_avg > overall_avg * 1.1:
            return "Recent improvements detected. Current adjustments are effective."
        elif recent_avg < overall_avg * 0.9:
            return "Performance declining. Consider more aggressive prompt changes."
        else:
            return "Performance stable. Fine-tune specific aspects."
