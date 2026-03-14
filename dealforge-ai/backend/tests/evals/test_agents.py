import pytest
from .conftest import calculate_accuracy, calculate_completeness, BENCHMARKS
from backend.app.agents.financial_analyst import FinancialAnalystAgent
from backend.app.agents.legal_advisor import LegalAdvisorAgent
# Import other agents as needed

@pytest.mark.asyncio
async def test_financial_analyst_accuracy(mock_financial_analyst):
    # Mock input data
    input_data = {"company": "TechCorp", "financials": {"revenue": 1000000}}
    ground_truth = "Expected analysis output"
    
    output = await mock_financial_analyst.run(task="analyze financials", context=input_data)
    # convert to string for matcher
    text_output = str(output.data or output.reasoning or output)
    accuracy = calculate_accuracy(text_output, ground_truth)
    assert accuracy >= BENCHMARKS['accuracy']

@pytest.mark.asyncio
async def test_financial_analyst_completeness(mock_financial_analyst):
    input_data = {"company": "TechCorp", "financials": {"revenue": 1000000}}
    required_elements = ["DCF", "LBO", "valuation"]
    
    output = await mock_financial_analyst.run(task="analyze financials", context=input_data)
    text_output = str(output.data or output.reasoning or output)
    completeness = calculate_completeness(text_output, required_elements)
    assert completeness >= BENCHMARKS['completeness']

@pytest.mark.asyncio
async def test_financial_analyst_error_handling(mock_financial_analyst):
    # Simulate error
    input_data = {"invalid": "data"}
    try:
        output = await mock_financial_analyst.run(task="analyze", context=input_data)
        text_output = str(output.data or output.reasoning or output)
        # Assert agent returns a failure object rather than crashing
        assert not output.success or "error" in text_output.lower()
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")

# Similar tests for other agents, e.g., legal_advisor

@pytest.mark.asyncio
async def test_legal_advisor_accuracy():
    # Fixture or mock here if not in conftest
    agent = LegalAdvisorAgent()  # use agent class; mocking may be needed separately
    input_data = {"contract": "Sample contract text"}
    ground_truth = "Expected legal analysis"
    
    output = await agent.run(task="Legal analysis", context=input_data)
    accuracy = calculate_accuracy(output, ground_truth)
    assert accuracy >= BENCHMARKS['accuracy']

# Add tests for tool usage, collaboration
# For collaboration, mock other agents

# Replication consistency test (part of quality overhaul)

@pytest.mark.asyncio
async def test_financial_analyst_replication(mock_financial_analyst):
    input_data = {"company": "TechCorp", "financials": {"revenue": 1000000}}
    outputs = []
    for _ in range(3):
        out = await mock_financial_analyst.run(task="analyze financials", context=input_data)
        outputs.append(str(out.data or out.reasoning or out))
    # calculate pairwise similarity
    from difflib import SequenceMatcher
    sims = []
    for i in range(len(outputs)):
        for j in range(i + 1, len(outputs)):
            sims.append(SequenceMatcher(None, outputs[i], outputs[j]).ratio())
    mean_sim = sum(sims) / len(sims) if sims else 1.0
    assert mean_sim >= BENCHMARKS['replication_consistency']

# More tests...

