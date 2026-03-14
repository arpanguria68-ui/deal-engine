import pytest
from unittest.mock import Mock
from .conftest import calculate_completeness, BENCHMARKS
from backend.app.core.reports.report_generator import generate_pptx, generate_excel

@pytest.mark.asyncio
async def test_report_completeness():
    generator = ReportGenerator()
    input_data = {"analysis": "Sample analysis data"}
    required_sections = ["Executive Summary", "Financials", "Risks"]
    
    report = await generator.generate(input_data)
    completeness = calculate_completeness(report, required_sections)
    assert completeness >= BENCHMARKS['completeness']

@pytest.mark.asyncio
async def test_report_accuracy():
    generator = ReportGenerator()
    input_data = {"analysis": "Accurate data"}
    ground_truth = "Expected report content"
    
    report = await generator.generate(input_data)
    accuracy = calculate_accuracy(report, ground_truth)
    assert accuracy >= BENCHMARKS['accuracy']

@pytest.mark.asyncio
async def test_report_error_handling():
    generator = ReportGenerator()
    input_data = {"invalid": "data"}
    
    try:
        report = await generator.generate(input_data)
        assert "default report" in report  # Assuming handling
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")

# More tests for formatting, etc.

