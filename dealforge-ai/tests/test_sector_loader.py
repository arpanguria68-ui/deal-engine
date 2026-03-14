import asyncio
from app.core.sector_loader import load_sector_config, build_sector_prompt
from app.agents.base import BaseAgent


def test_sector_loader():
    print("Testing Sector Loader (Tech)...")
    tech_cfg = load_sector_config("tech")
    assert tech_cfg is not None, "Failed to load tech.yaml"
    assert tech_cfg.get("sector") == "technology", "Wrong sector mapped"

    print("Testing Sector Prompt Builder...")
    prompt = build_sector_prompt("financial_analyst", tech_cfg)
    print("Injected Prompt:")
    print(prompt)

    assert (
        "Recurring revenue" in prompt or "recurring revenue" in prompt
    ), "Failed to inject custom prompt"
    assert "Cloud infrastructure lock-in risk" in prompt, "Failed to inject checklists"


def test_fallback():
    print("\nTesting Invalid Sector Loader (Fallback)...")
    invalid_cfg = load_sector_config("biotech_unknown")
    assert invalid_cfg == {}, "Fallback should return empty dict"


if __name__ == "__main__":
    test_sector_loader()
    test_fallback()
    print("\nAll internal sanity tests passed!")
