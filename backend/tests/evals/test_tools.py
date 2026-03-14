import pytest
from unittest.mock import Mock
from .conftest import calculate_accuracy, BENCHMARKS
from backend.app.core.tools.finance_toolkit_tool import FinanceAnalysisTool as FinanceToolkitTool
# Import other tools

@pytest.mark.asyncio
async def test_finance_toolkit_accuracy(mock_api_tool):
    tool = FinanceToolkitTool()
    tool.api_client = mock_api_tool
    input_data = {"symbol": "AAPL", "metric": "revenue"}
    ground_truth = {"revenue": 1000000000}
    
    output = await tool.execute(input_data)
    accuracy = calculate_accuracy(str(output), str(ground_truth))
    assert accuracy >= BENCHMARKS['accuracy']

@pytest.mark.asyncio
async def test_finance_toolkit_error_handling(mock_api_tool):
    mock_api_tool.execute.side_effect = Exception("API Error")
    tool = FinanceToolkitTool(api_client=mock_api_tool)
    input_data = {"symbol": "INVALID"}
    
    try:
        output = await tool.execute(input_data)
        assert "error handled" in output
    except Exception as e:
        assert str(e) == "API Error"  # or check if handled properly

# Tests for tool usage efficiency, perhaps count calls

# Similar tests for other tools like alpha_vantage_tool, etc.

