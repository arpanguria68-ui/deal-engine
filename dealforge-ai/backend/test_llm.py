import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path to allow imports
sys.path.append(os.getcwd())

from app.core.llm import get_llm_client
from app.config import get_settings


async def test_llm_connections():
    load_dotenv()
    settings = get_settings()

    # Test configured providers
    providers = ["gemini", "openai", "mistral", "lmstudio"]

    print("🤖 Testing LLM Connections...")
    print("-" * 30)

    for provider in providers:
        print(f"Testing {provider}...", end=" ", flush=True)
        try:
            client = get_llm_client(provider)
            # Short prompt to verify connectivity
            response = await client.generate(
                prompt="Hi, just reply with 'OK'", system_prompt="Verification mode"
            )
            if "OK" in response.get("content", "").upper():
                print("✅ CONNECTED")
            else:
                print(f"⚠️ CONNECTED (Unexpected response: {response.get('content')})")
        except Exception as e:
            print(f"❌ FAILED: {str(e)[:100]}")


if __name__ == "__main__":
    asyncio.run(test_llm_connections())
