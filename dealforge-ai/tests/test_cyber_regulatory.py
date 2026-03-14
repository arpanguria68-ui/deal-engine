import asyncio
import json
from app.core.tools.regulatory_tools import (
    CyberVulnScannerTool,
    AntitrustHHICalculatorTool,
    PrivacyAuditorTool,
)
from app.agents.compliance_qa_agent import ComplianceQAAgent


def test_regulatory_tools():
    print("Testing Cyber Vuln Scanner...")
    scanner = CyberVulnScannerTool()
    vuln_text = "We recently suffered a ransomware attack resulting in a massive data breach. Furthermore, we are not SOC2 compliant."
    res1 = scanner.execute(security_text=vuln_text)
    print("Scanner Result:", json.dumps(res1.data, indent=2))
    assert (
        res1.data["vulnerabilities_count"] == 3
    ), "Failed to detect all vulnerabilities"
    assert res1.data["compliance_flags"] == "High Risk", "Failed to flag as High Risk"

    print("\nTesting Antitrust HHI Calculator...")
    calculator = AntitrustHHICalculatorTool()
    shares = [0.40, 0.20, 0.15]
    res2 = calculator.execute(market_shares=shares)
    print("Calculator Result:", json.dumps(res2.data, indent=2))
    assert (
        res2.data["calculated_hhi"] == 2225.0
    ), "HHI Calculation is mathematically incorrect"
    assert (
        res2.data["risk_classification"] == "Moderate Concentration"
    ), "Wrong HHI Classification"

    print("\nTesting Privacy Auditor...")
    auditor = PrivacyAuditorTool()
    privacy_text = (
        "We store EU user data in the US, but we have no DPO for GDPR matters."
    )
    res3 = auditor.execute(data_flow_text=privacy_text)
    print("Privacy Auditor Result:", json.dumps(res3.data, indent=2))
    assert res3.data["audit_status"] == "Failed", "Failed to catch privacy violation"


def test_agent_integration():
    print("\nTesting Compliance Agent Init...")
    agent = ComplianceQAAgent()
    assert agent.name == "compliance_qa_agent"
    print(
        "Agent init successful. Skipping live LLM integration in deterministic test suite."
    )


if __name__ == "__main__":
    test_regulatory_tools()
    test_agent_integration()
    print("\nAll internal sanity tests passed!")
