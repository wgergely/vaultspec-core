"""Vault CLI — audit, create, index, and search .vault/ documents."""

import argparse
import json
import logging
import sys
from datetime import datetime

from .cli_common import (
    add_common_args,
    get_default_layout,
    resolve_args_workspace,
    setup_logging,
)
from .graph import VaultGraph
from .metrics import get_vault_metrics
from .vaultcore import (
    DocType,
    create_vault_doc,
)
from .verification import (
    fix_violations,
    get_malformed,
    list_features,
    verify_vertical_integrity,
)

logger = logging.getLogger(__name__)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit and manage the .vault vault.")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Audit the vault.")
    audit_parser.add_argument(
        "--summary", action="store_true", help="Show summary stats."
    )
    audit_parser.add_argument(
        "--features", action="store_true", help="List all features."
    )
    audit_parser.add_argument(
        "--verify", action="store_true", help="Run full verification."
    )
    audit_parser.add_argument(
        "--graph", action="store_true", help="Show graph hotspots."
    )
    audit_parser.add_argument(
        "--limit", type=int, default=10, help="Limit number of items in reports."
    )
    audit_parser.add_argument("--type", type=str, help="Filter hotspots by DocType.")
    audit_parser.add_argument(
        "--feature", type=str, help="Filter hotspots by feature tag."
    )
    audit_parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format."
    )
    audit_parser.add_argument(
        "--fix", action="store_true", help="Auto-repair common violations."
    )

    # Create command
    create_parser = subparsers.add_parser(
        "create", help="Create a new doc from template."
    )
    create_parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=[dt.value for dt in DocType],
        help="Type of doc to create.",
    )
    create_parser.add_argument(
        "--feature", type=str, required=True, help="Feature name (kebab-case)."
    )
    create_parser.add_argument("--title", type=str, help="Title of the document.")

    # Index command (RAG)
    index_parser = subparsers.add_parser(
        "index",
        help="Index vault documents for semantic search.",
        epilog=(
            "NOTE: Requires NVIDIA GPU with CUDA. CPU-only systems are not supported."
        ),
    )
    index_parser.add_argument(
        "--full",
        action="store_true",
        help="Force full re-index (default: incremental).",
    )
    index_parser.add_argument(
        "--json", action="store_true", help="Output result as JSON."
    )

    # Search command (RAG)
    search_parser = subparsers.add_parser(
        "search",
        help="Semantic search over vault documents.",
        epilog=(
            "NOTE: Requires NVIDIA GPU with CUDA. CPU-only systems are not supported."
        ),
    )
    search_parser.add_argument("query", type=str, help="Search query.")
    search_parser.add_argument(
        "--limit", type=int, default=5, help="Number of results."
    )
    search_parser.add_argument(
        "--json", action="store_true", help="Output results as JSON."
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _make_parser()
    args = parser.parse_args(argv)

    setup_logging(args)

    if not args.command:
        parser.print_help()
        return

    resolve_args_workspace(args, get_default_layout())

    if args.command == "create":
        handle_create(args)
    elif args.command == "audit":
        handle_audit(args)
    elif args.command == "index":
        handle_index(args)
    elif args.command == "search":
        handle_search(args)


def handle_create(args):
    doc_type = DocType(args.type)
    feature = args.feature.strip("#")
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        create_vault_doc(args.root, doc_type, feature, date_str, args.title)
    except FileNotFoundError as exc:
        logger.error("Error: %s", exc)
        sys.exit(1)
    except FileExistsError as exc:
        logger.error("Error: %s", exc)
        sys.exit(1)


def handle_audit(args):
    root_dir = args.root
    results = {}

    if args.summary:
        metrics = get_vault_metrics(root_dir)
        results["summary"] = {
            "total_docs": metrics.total_docs,
            "total_features": metrics.total_features,
            "counts_by_type": {
                dt.value: count for dt, count in metrics.counts_by_type.items()
            },
        }
        if not args.json:
            print("Vault Summary:")
            print(f"  Total Documents: {metrics.total_docs}")
            print(f"  Total Features:  {metrics.total_features}")
            print("  By Type:")
            for dt_val, count in results["summary"]["counts_by_type"].items():
                print(f"    {dt_val:10}: {count}")
            print()

    if args.features:
        features = list_features(root_dir)
        results["features"] = sorted(features)
        if not args.json:
            print(f"Features ({len(features)}):")
            for f in results["features"]:
                print(f"  - {f}")
            print()

    if args.verify:
        errors = get_malformed(root_dir)
        errors.extend(verify_vertical_integrity(root_dir))

        results["verification"] = {
            "passed": len(errors) == 0,
            "errors": [{"path": str(e.path), "message": e.message} for e in errors],
        }
        if not args.json:
            if errors:
                print(f"Verification Failed ({len(errors)} errors):")
                for err in errors:
                    print(f"  {err}")
            else:
                print("Verification Passed.")
            print()

        if args.fix and errors:
            if not args.json:
                print("Running auto-repair...")
            fixes = fix_violations(root_dir)
            results["fixes"] = [
                {
                    "path": str(f.path),
                    "action": f.action,
                    "detail": f.detail,
                }
                for f in fixes
            ]
            if not args.json:
                if fixes:
                    print(f"\nApplied {len(fixes)} fixes:")
                    for fix in fixes:
                        print(f"  {fix}")
                else:
                    print("\nNo auto-fixable violations found.")
                print()

    if args.graph:
        graph = VaultGraph(root_dir)
        doc_type_filter = DocType(args.type) if args.type else None

        hotspots = graph.get_hotspots(
            limit=args.limit, doc_type=doc_type_filter, feature=args.feature
        )

        results["graph"] = {
            "hotspots": [{"name": name, "count": count} for name, count in hotspots]
        }

        if not args.json:
            title = "Graph Hotspots"
            if doc_type_filter:
                title += f" (Type: {doc_type_filter.value})"
            if args.feature:
                title += f" (Feature: {args.feature})"
            print(f"{title}:")
            for name, count in hotspots:
                print(f"  {name:30}: {count} incoming links")

        if not args.type and not args.feature:
            f_rankings = graph.get_feature_rankings(limit=args.limit)
            results["graph"]["feature_rankings"] = [
                {"feature": f, "count": c} for f, c in f_rankings
            ]
            if not args.json:
                print("\nHottest Features (Cumulative Links):")
                for f_name, count in f_rankings:
                    print(f"  {f_name:30}: {count} total incoming links")

        invalid = graph.get_invalid_links()
        results["graph"]["invalid_links"] = [
            {"source": s, "target": t} for s, t in invalid
        ]
        if not args.json and invalid:
            print(f"\nInvalid Links ({len(invalid)}):")
            for source, target in invalid:
                print(f"  {source} -> [[{target}]] (Target not found)")

        orphans = graph.get_orphaned()
        results["graph"]["orphans"] = orphans
        if not args.json and orphans:
            print(f"\nOrphaned Documents ({len(orphans)}):")
            for name in orphans:
                print(f"  - {name}")
            print()

    if args.json:
        print(json.dumps(results, indent=2))


def handle_index(args):
    try:
        from .rag import get_device_info, index
    except ImportError:
        logger.error("Error: RAG dependencies not installed.")
        logger.error("Run: pip install -e '.[rag]'")
        sys.exit(1)

    root_dir = args.root

    device_info = get_device_info()
    if not args.json:
        device = device_info["device"]
        gpu = device_info.get("gpu_name")
        if gpu:
            vram = device_info.get("vram_mb", 0)
            logger.info("Device: %s (%s, %dMB VRAM)", device, gpu, vram)
        else:
            logger.info("Device: %s", device)

    if not args.json:
        msg = "Running full index..." if args.full else "Running incremental index..."
        logger.info(msg)

    result = index(root_dir, full=args.full)

    if args.json:
        print(
            json.dumps(
                {
                    "total": result.total,
                    "added": result.added,
                    "updated": result.updated,
                    "removed": result.removed,
                    "duration_ms": result.duration_ms,
                    "device": result.device,
                },
                indent=2,
            )
        )
    else:
        logger.info("Index complete:")
        logger.info("  Total documents: %d", result.total)
        logger.info("  Added:           %d", result.added)
        logger.info("  Updated:         %d", result.updated)
        logger.info("  Removed:         %d", result.removed)
        logger.info("  Duration:        %dms", result.duration_ms)
        logger.info("  Device:          %s", result.device)


def handle_search(args):
    try:
        from .rag import search
    except ImportError:
        logger.error("Error: RAG dependencies not installed.")
        logger.error("Run: pip install -e '.[rag]'")
        sys.exit(1)

    root_dir = args.root
    results = search(root_dir, args.query, limit=args.limit)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "path": r.path,
                        "title": r.title,
                        "doc_type": r.doc_type,
                        "feature": r.feature,
                        "date": r.date,
                        "score": round(r.score, 4),
                        "snippet": r.snippet,
                    }
                    for r in results
                ],
                indent=2,
            )
        )
    else:
        if not results:
            logger.info("No results found for '%s'.", args.query)
            logger.info("Try broadening your query or removing filters.")
            return
        print(f"Search results for '{args.query}':")
        for r in results:
            print(f"  [{r.score:.2f}] {r.path} (#{r.feature})")
            print(f"         {r.title}")


if __name__ == "__main__":
    main()
