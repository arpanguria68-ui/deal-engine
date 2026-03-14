import asyncio
from app.core.tools.alpha_vantage_tool import AlphaVantageTool
from app.core.tools.finnhub_tool import FinnhubTool
from app.core.tools.financial_datasets_tool import FinancialDatasetsTool


async def main():
    print("Testing AlphaVantageTool initialization...")
    av_tool = AlphaVantageTool()
    print("Success: AlphaVantageTool")

    print("\nTesting FinnhubTool initialization...")
    fh_tool = FinnhubTool()
    print("Success: FinnhubTool")

    print("\nTesting FinancialDatasetsTool...")
    fd_tool = FinancialDatasetsTool()
    print("Success: FinancialDatasetsTool")


if __name__ == "__main__":
    asyncio.run(main())
