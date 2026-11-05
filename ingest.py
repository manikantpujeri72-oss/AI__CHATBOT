"""Command-line interface for managing the MCE AI Assistant knowledge base.

Usage:
  python ingest.py [--sync] [--dry-run]
  python ingest.py --add <file> [--as <path-in-documents>]
  python ingest.py --replace <old-source> <new-file>
  python ingest.py --delete <source>
  python ingest.py --list
  python ingest.py --reset
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import rag

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


def check_api_key() -> None:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        print("ERROR: COHERE_API_KEY is missing. Please add it to your .env file.")
        sys.exit(1)


def format_sync_report(report: dict) -> None:
    is_dry = report.get("dry_run", False)
    prefix = "[DRY RUN] " if is_dry else ""

    for item in report.get("added", []):
        src = item["source"]
        chunks = item["chunks"]
        print(f"{prefix}ADDED {src} ({chunks} chunks added)")

    for item in report.get("updated", []):
        src = item["source"]
        old_n = item["old_chunks"]
        new_n = item["new_chunks"]
        print(f"{prefix}UPDATED {src} ({old_n} old chunks removed, {new_n} new chunks added)")

    for item in report.get("renamed", []):
        old_src = item["old_source"]
        new_src = item["new_source"]
        chunks = item["chunks"]
        print(f"{prefix}RENAMED {old_src} -> {new_src} ({chunks} chunks)")

    for item in report.get("removed", []):
        src = item["source"]
        chunks = item["chunks"]
        print(f"{prefix}REMOVED {src} ({chunks} chunks removed)")

    for src in report.get("unchanged", []):
        print(f"{prefix}UNCHANGED {src}")

    for item in report.get("failed", []):
        src = item["source"]
        reason = item["reason"]
        print(f"{prefix}FAILED {src}: {reason}")

    added_cnt = len(report.get("added", []))
    updated_cnt = len(report.get("updated", []))
    renamed_cnt = len(report.get("renamed", []))
    unchanged_cnt = len(report.get("unchanged", []))
    removed_cnt = len(report.get("removed", []))
    failed_cnt = len(report.get("failed", []))

    total_chunks = sum(report.get("chunk_counts", {}).values())
    print("-" * 60)
    print(
        f"{prefix}Sync summary: {added_cnt} added, {updated_cnt} updated, {renamed_cnt} renamed, "
        f"{unchanged_cnt} unchanged, {removed_cnt} removed, {failed_cnt} failed."
    )
    if not is_dry:
        print(f"Total chunks in database: {total_chunks}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MCE AI Assistant Knowledge Base Ingestion & Sync CLI"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        default=False,
        help="Synchronise documents folder with ChromaDB (default action)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes that would occur without modifying the database or disk",
    )
    parser.add_argument(
        "--add",
        metavar="FILE",
        help="Add or update a document in the knowledge base",
    )
    parser.add_argument(
        "--as",
        dest="as_path",
        metavar="PATH",
        help="Target relative path inside documents/ when using --add",
    )
    parser.add_argument(
        "--replace",
        nargs=2,
        metavar=("OLD_SOURCE", "NEW_FILE"),
        help="Replace an existing document with a new file (even if names differ)",
    )
    parser.add_argument(
        "--delete",
        metavar="SOURCE",
        help="Delete a document (removes its chunks and moves file to documents/_deleted/)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="List all indexed documents, chunk counts, page counts, and last indexed time",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Wipe the database collection and re-index all files in documents/",
    )
    parser.add_argument(
        "--faculty",
        action="store_true",
        default=False,
        help="Rebuild structured faculty data and photos from documents/",
    )

    args = parser.parse_args()

    # Determine command
    is_explicit_cmd = bool(
        args.add or args.replace or args.delete or args.list or args.reset or args.sync or args.faculty
    )
    run_sync = args.sync or (not is_explicit_cmd)

    if args.faculty:
        print("Extracting faculty structured data and photos from documents/...")
        import faculty_extractor
        records = faculty_extractor.extract_all_faculty()
        print(f"Successfully extracted {len(records)} faculty records into faculty.json and assets/faculty/.")
        return

    # All operations except --list (when DB exists) and --dry-run may need Cohere
    # But check API key uniformly for safety
    if not args.list:
        check_api_key()

    cohere_client = None
    if not args.list and not args.dry_run:
        cohere_client = rag.get_cohere_client()
    elif not args.list and args.dry_run:
        # Dry-run sync doesn't require Cohere calls
        pass

    collection = rag.get_collection()

    if args.reset:
        print("Resetting database collection...")
        rag.reset_collection()
        collection = rag.get_collection()
        print("Rebuilding collection from documents folder...")
        if cohere_client is None:
            cohere_client = rag.get_cohere_client()
        report = rag.sync_documents(cohere_client, collection, dry_run=False)
        format_sync_report(report)
        return

    if args.list:
        sources = rag.list_sources(collection)
        if not sources:
            print("Knowledge base is empty. (0 documents indexed)")
            return
        total_chunks = sum(s["chunks"] for s in sources.values())
        print(f"Indexed documents ({len(sources)} files, {total_chunks} total chunks):")
        print("-" * 80)
        for name, info in sources.items():
            ts = info.get("indexed_at", "N/A")
            h = info.get("file_hash", "N/A")
            print(
                f"  • {name:<45} | {info['chunks']:>3} chunks | {info['pages']:>2} pages | "
                f"sha1:{h} | updated: {ts}"
            )
        return

    if args.add:
        file_path = Path(args.add)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)
        data = file_path.read_bytes()
        dest_name = args.as_path or file_path.name
        status = rag.add_or_replace_document(
            client=cohere_client,
            collection=collection,
            filename=dest_name,
            data=data,
        )
        sources = rag.list_sources(collection)
        chunk_count = sources.get(dest_name, {}).get("chunks", 0)
        if status == "added":
            print(f"ADDED {dest_name} ({chunk_count} chunks)")
        elif status == "replaced":
            print(f"REPLACED {dest_name} ({chunk_count} chunks)")
        else:
            print(f"UNCHANGED {dest_name} (identical content already indexed)")
        return

    if args.replace:
        old_source, new_file = args.replace
        new_path = Path(new_file)
        if not new_path.exists():
            print(f"ERROR: Replacement file not found: {new_path}")
            sys.exit(1)
        data = new_path.read_bytes()
        rag.replace_document_with(
            client=cohere_client,
            collection=collection,
            old_source=old_source,
            new_filename=new_path.name,
            data=data,
        )
        sources = rag.list_sources(collection)
        new_chunks = sources.get(new_path.name, {}).get("chunks", 0)
        print(f"REPLACED {old_source} with {new_path.name} ({new_chunks} new chunks added)")
        return

    if args.delete:
        source = args.delete
        rag.delete_document(collection=collection, source=source)
        print(f"DELETED {source} (chunks removed from database; file moved to documents/_deleted/)")
        return

    if run_sync:
        if args.dry_run:
            report = rag.sync_documents(cohere_client, collection, dry_run=True)
            format_sync_report(report)
        else:
            report = rag.sync_documents(cohere_client, collection, dry_run=False)
            format_sync_report(report)


if __name__ == "__main__":
    main()
