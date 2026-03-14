import os
import json
import difflib
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "../../../data/report_versions")
os.makedirs(VERSIONS_DIR, exist_ok=True)


class ReportVersioningService:
    @staticmethod
    def save_version(
        deal_id: str, report_type: str, content: str, author: str = "system"
    ) -> str:
        """
        Saves a new version of a generated report (e.g. PDF markdown representation, or HTML body).
        Returns the new version ID.
        """
        version_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        deal_dir = os.path.join(VERSIONS_DIR, deal_id)
        os.makedirs(deal_dir, exist_ok=True)

        # Determine next version number
        existing = [
            f
            for f in os.listdir(deal_dir)
            if f.startswith(f"{report_type}_v") and f.endswith(".json")
        ]
        next_v = len(existing) + 1

        filename = f"{report_type}_v{next_v}_{version_id}.json"
        filepath = os.path.join(deal_dir, filename)

        data = {
            "version_id": version_id,
            "version": next_v,
            "deal_id": deal_id,
            "report_type": report_type,
            "author": author,
            "timestamp": timestamp,
            "content": content,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(
            "report_version_saved",
            deal_id=deal_id,
            report_type=report_type,
            version=next_v,
        )
        return version_id

    @staticmethod
    def list_versions(deal_id: str, report_type: str) -> List[Dict[str, Any]]:
        """List all available versions for a deal's report type."""
        deal_dir = os.path.join(VERSIONS_DIR, deal_id)
        if not os.path.exists(deal_dir):
            return []

        versions = []
        for filename in os.listdir(deal_dir):
            if filename.startswith(f"{report_type}_v") and filename.endswith(".json"):
                with open(os.path.join(deal_dir, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    versions.append(
                        {
                            "version_id": data["version_id"],
                            "version": data["version"],
                            "author": data["author"],
                            "timestamp": data["timestamp"],
                        }
                    )

        # Sort by version number descending
        return sorted(versions, key=lambda x: x["version"], reverse=True)

    @staticmethod
    def get_diff(
        deal_id: str, report_type: str, v1_num: int, v2_num: int
    ) -> Optional[str]:
        """
        Generate a text diff between two versions of a report.
        """
        deal_dir = os.path.join(VERSIONS_DIR, deal_id)
        if not os.path.exists(deal_dir):
            return None

        v1_data, v2_data = None, None

        for filename in os.listdir(deal_dir):
            if filename.startswith(f"{report_type}_v{v1_num}_"):
                with open(os.path.join(deal_dir, filename), "r", encoding="utf-8") as f:
                    v1_data = json.load(f)
            elif filename.startswith(f"{report_type}_v{v2_num}_"):
                with open(os.path.join(deal_dir, filename), "r", encoding="utf-8") as f:
                    v2_data = json.load(f)

        if not v1_data or not v2_data:
            return None

        text1 = v1_data.get("content", "").splitlines()
        text2 = v2_data.get("content", "").splitlines()

        diff = difflib.unified_diff(
            text1, text2, fromfile=f"v{v1_num}", tofile=f"v{v2_num}", lineterm=""
        )
        return "\\n".join(diff)
