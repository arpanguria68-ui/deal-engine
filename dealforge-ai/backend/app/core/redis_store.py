import json
import os
import structlog
from typing import Dict, Any, List, Optional
import redis.asyncio as redis

logger = structlog.get_logger()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RedisStore:
    _instance: Optional["RedisStore"] = None

    def __init__(self):
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("redis_store_initialized", url=REDIS_URL)

    @classmethod
    def get_instance(cls) -> "RedisStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ═══════════════════════════════════════════════════════════
    #  Deal Store Operations
    # ═══════════════════════════════════════════════════════════

    async def get_deal(self, deal_id: str) -> Optional[Dict[str, Any]]:
        data = await self.client.get(f"deal:{deal_id}")
        if data:
            return json.loads(data)
        return None

    async def save_deal(self, deal_id: str, deal_data: Dict[str, Any]):
        await self.client.set(f"deal:{deal_id}", json.dumps(deal_data))

    async def list_deals(self) -> List[Dict[str, Any]]:
        keys = await self.client.keys("deal:*")
        deals = []
        for key in keys:
            data = await self.client.get(key)
            if data:
                deals.append(json.loads(data))
        return deals

    async def update_deal(self, deal_id: str, update_data: Dict[str, Any]):
        deal = await self.get_deal(deal_id)
        if deal:
            deal.update(update_data)
            await self.save_deal(deal_id, deal)

    async def delete_deal(self, deal_id: str):
        await self.client.delete(f"deal:{deal_id}")
        await self.client.delete(f"activity:{deal_id}")

    # ═══════════════════════════════════════════════════════════
    #  Agent Activity Operations
    # ═══════════════════════════════════════════════════════════

    async def add_activity(self, evt: dict):
        deal_id = evt.get("deal_id")
        if deal_id:
            await self.client.rpush(f"activity:{deal_id}", json.dumps(evt))

        # Keep global activity log (recent 1000 events)
        await self.client.rpush("global_activity", json.dumps(evt))
        await self.client.ltrim("global_activity", -1000, -1)

    async def get_deal_activity(self, deal_id: str) -> List[dict]:
        items = await self.client.lrange(f"activity:{deal_id}", 0, -1)
        return [json.loads(i) for i in items]

    async def get_global_activity(self) -> List[dict]:
        items = await self.client.lrange("global_activity", 0, -1)
        return [json.loads(i) for i in items]

    # ═══════════════════════════════════════════════════════════
    #  Conversation Store Operations
    # ═══════════════════════════════════════════════════════════

    async def save_conversation(self, conv_id: str, conv_data: Dict[str, Any]):
        """Save or update a full conversation."""
        await self.client.set(f"conv:{conv_id}", json.dumps(conv_data))
        # Track in sorted set for ordered listing (score = updatedAt timestamp)
        updated_at = conv_data.get("updatedAt", 0)
        await self.client.zadd("conv_index", {conv_id: updated_at})

    async def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        data = await self.client.get(f"conv:{conv_id}")
        if data:
            return json.loads(data)
        return None

    async def list_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List conversations ordered by most recently updated."""
        # Get conv IDs from sorted set, newest first
        conv_ids = await self.client.zrevrange("conv_index", 0, limit - 1)
        conversations = []
        for conv_id in conv_ids:
            data = await self.client.get(f"conv:{conv_id}")
            if data:
                conversations.append(json.loads(data))
            else:
                # Stale index entry — clean up
                await self.client.zrem("conv_index", conv_id)
        return conversations

    async def delete_conversation(self, conv_id: str):
        await self.client.delete(f"conv:{conv_id}")
        await self.client.zrem("conv_index", conv_id)

    async def clear_all_conversations(self):
        """Delete all conversations and the index."""
        conv_ids = await self.client.zrange("conv_index", 0, -1)
        if conv_ids:
            keys = [f"conv:{cid}" for cid in conv_ids]
            await self.client.delete(*keys)
        await self.client.delete("conv_index")

    async def close(self):
        await self.client.aclose()
