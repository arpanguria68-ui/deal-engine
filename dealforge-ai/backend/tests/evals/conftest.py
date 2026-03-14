import pytest
from unittest.mock import Mock, patch
import difflib

# Assuming pytest_asyncio is installed for async tests
import pytest_asyncio

# Mock external providers and APIs
@pytest.fixture
def mock_llm_client():
    mock = Mock()
    mock.generate.return_value = "Mock LLM response"
    return mock

@pytest.fixture
def mock_api_tool():
    mock = Mock()
    mock.execute.return_value = {"mock_data": "value"}
    return mock

# Metrics calculation functions
def calculate_accuracy(output, ground_truth):
    """Calculate accuracy using sequence matcher."""
    matcher = difflib.SequenceMatcher(None, output, ground_truth)
    return matcher.ratio()

def calculate_completeness(output, required_elements):
    """Calculate completeness as proportion of required elements present."""
    present = sum(1 for elem in required_elements if elem in output)
    return present / len(required_elements) if required_elements else 1.0

# Add more metrics as needed: tool_usage, etc.

# Benchmarks
BENCHMARKS = {
    'accuracy': 0.90,
    'completeness': 0.95,
    'tool_usage_efficiency': 0.80,
    'error_recovery': 0.85,
    'replication_consistency': 0.95,
    # Add others from framework
}

# Fixtures for key components
@pytest_asyncio.fixture
async def mock_financial_analyst(mock_llm_client):
    from backend.app.agents.financial_analyst import FinancialAnalystAgent
    agent = FinancialAnalystAgent(llm_client=mock_llm_client)
    return agent

# Similarly for other agents, tools, etc.
# We can add more in individual test files if needed

