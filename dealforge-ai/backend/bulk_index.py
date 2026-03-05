"""
Bulk Document Ingestion Tool for DealForge AI
Allows indexing large volumes of documents from a local directory.
"""

import os
import asyncio
import argparse
import sys
from pathlib import Path

# Add the current directory to sys.path to ensure 'app' imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.memory.local_pageindex import get_local_pageindex
from app.config import get_settings


async def bulk_index(directory: str, deal_id: str = None):
    """
    Scans a directory for documents and indexes them into PageIndex.
    """
    service = get_local_pageindex()

    supported_extensions = {".pdf", ".docx", ".md", ".txt", ".markdown"}
    path = Path(directory)

    if not path.is_dir():
        print(f"\033[91mError: {directory} is not a directory.\033[0m")
        return

    print(f"\n\033[94mScanning directory:\033[0m {path.absolute()}")

    files_to_index = []
    for root, _, files in os.walk(directory):
        for file in files:
            if Path(file).suffix.lower() in supported_extensions:
                files_to_index.append(Path(root) / file)

    if not files_to_index:
        print("\033[93mNo supported files found (.pdf, .docx, .md, .txt).\033[0m")
        return

    print(f"\033[92mFound {len(files_to_index)} files for indexing.\033[0m\n")

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(files_to_index):
        print(
            f"[{i+1}/{len(files_to_index)}] Indexing: {file_path.name}...",
            end="",
            flush=True,
        )
        try:
            # Index document
            await service.index_document(
                str(file_path),
                metadata={"deal_id": deal_id, "ingestion_method": "bulk_tool"},
            )
            print(" \033[92mDone.\033[0m")
            success_count += 1
        except Exception as e:
            print(f" \033[91mFailed: {str(e)}\033[0m")
            fail_count += 1

    print(f"\n\033[94m--- Bulk Ingestion Complete ---\033[0m")
    print(f"Successfully Indexed: {success_count}")
    print(f"Failed:               {fail_count}")

    stats = service.get_stats()
    print(f"Total Knowledge Base Size: {stats.get('storage_mb', 0)} MB")
    print(f"Total Indexed Documents:   {stats.get('total_documents', 0)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bulk index documents into DealForge AI Knowledge Base"
    )
    parser.add_argument("directory", help="Local directory containing documents")
    parser.add_argument(
        "--deal-id",
        help="Optional Deal ID to associate with these documents",
        default=None,
    )

    args = parser.parse_args()

    try:
        asyncio.run(bulk_index(args.directory, args.deal_id))
    except KeyboardInterrupt:
        print("\n\033[93mIngestion cancelled by user.\033[0m")
