import asyncio
import os
import sys

# Add backend to path
backend_path = os.path.abspath(
    r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend"
)
if backend_path not in sys.path:
    sys.path.append(backend_path)


async def test_search_fallback():
    print("Testing Search Fallback Logic...")
    from app.core.mcp import get_mcp_router, _runtime_keys

    router = get_mcp_router()

    # 1. Test default priority
    print("\n[Test 1] Default Priority")
    _runtime_keys["search_priority"] = ["serper", "searxng", "ddg"]
    # Mocking client results would be better, but we can at least check if it attempts the right ones
    # For now, let's just check the runtime keys behavior
    print(f"Current Priority in runtime keys: {_runtime_keys['search_priority']}")

    # 2. Test Custom Priority
    print("\n[Test 2] Custom Priority")
    _runtime_keys["search_priority"] = ["ddg", "serper"]
    print(f"Updated Priority in runtime keys: {_runtime_keys['search_priority']}")

    # 3. Test Routing via SettingsService
    print("\n[Test 3] SettingsService Sync")
    from app.core.settings_service import SettingsService

    svc = SettingsService.get_instance()
    svc.update({"search_priority": ["searxng", "ddg", "serper"]})

    print(
        f"Priority after SettingsService update: {_runtime_keys.get('search_priority')}"
    )

    if _runtime_keys.get("search_priority") == ["searxng", "ddg", "serper"]:
        print("✅ SUCCESS: SettingsService synced correctly with MCP runtime keys.")
    else:
        print("❌ FAILURE: Priority mismatch.")


if __name__ == "__main__":
    asyncio.run(test_search_fallback())
