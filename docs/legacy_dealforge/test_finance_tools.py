import asyncio
from app.core.tools.finance_database_tool import PeerDiscoveryTool
from app.core.tools.finance_toolkit_tool import FinanceAnalysisTool
import sys


async def main():
    print("Testing PeerDiscoveryTool...")
    peer_tool = PeerDiscoveryTool()
    res1 = peer_tool.execute(sector="Technology", industry="Software - Infrastructure")
    print(f"Peer Tool Success: {res1.success}")
    if res1.success:
        print(f"Found {res1.data.get('count_returned')} peers.")
        if res1.data.get("peers"):
            print(f"Sample: {res1.data['peers'][0]}")
    else:
        print(f"Error: {res1.error}")

    print(
        "\nTesting FinanceAnalysisTool (Skipping actual fetch if no FMP key is in config, just verifying instantiation)..."
    )
    fin_tool = FinanceAnalysisTool()
    print("FinanceAnalysisTool initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
