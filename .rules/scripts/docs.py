import argparse
import importlib.util
import json
import pathlib
import sys
from datetime import datetime

# Add lib/src to path
SCRIPTS_DIR = pathlib.Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent.parent
LIB_SRC = str(ROOT_DIR / ".rules" / "lib" / "src")
if LIB_SRC not in sys.path:
    sys.path.insert(0, LIB_SRC)


# Dynamic imports to avoid E402 without noqa
def _import_internal(name):
    return importlib.import_module(name)


def main():
    # Pre-load internal modules
    graph_api = _import_internal("graph.api")
    metrics_api = _import_internal("metrics.api")
    vault_hydration = _import_internal("vault.hydration")
    vault_models = _import_internal("vault.models")
    vault_rag = _import_internal("vault.rag")
    verification_api = _import_internal("verification.api")

    parser = argparse.ArgumentParser(description="Audit and manage the .docs vault.")
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
        "--root", type=str, default=str(ROOT_DIR), help="Vault root directory."
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

    # Create command
    create_parser = subparsers.add_parser(
        "create", help="Create a new doc from template."
    )
    create_parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=[dt.value for dt in vault_models.DocType],
        help="Type of doc to create.",
    )
    create_parser.add_argument(
        "--feature", type=str, required=True, help="Feature name (kebab-case)."
    )
    create_parser.add_argument("--title", type=str, help="Title of the document.")
    create_parser.add_argument(
        "--root", type=str, default=str(ROOT_DIR), help="Vault root directory."
    )

    # Index command
    index_parser = subparsers.add_parser(
        "index", help="Index vault for semantic search."
    )
    index_parser.add_argument("--root", default=".", help="Root directory.")
    index_parser.add_argument("--force", action="store_true", help="Force re-indexing.")
    index_parser.add_argument(
        "--limit", type=int, help="Limit number of docs to index."
    )

    # Search command
    search_parser = subparsers.add_parser("search", help="Semantic search in vault.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--root", default=".", help="Root directory.")
    search_parser.add_argument("--limit", type=int, default=5, help="Result limit.")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        handle_create(args, vault_models, vault_hydration)
    elif args.command == "audit":
        handle_audit(args, metrics_api, verification_api, graph_api, vault_models)
    elif args.command == "index":
        import asyncio

        asyncio.run(handle_index(args, vault_rag))
    elif args.command == "search":
        import asyncio

        asyncio.run(handle_search(args, vault_rag))


async def handle_index(args, vault_rag):
    root_dir = pathlib.Path(args.root)
    await vault_rag.index_vault(
        root_dir, force=args.force, project_root=ROOT_DIR, limit=args.limit
    )


async def handle_search(args, vault_rag):
    root_dir = pathlib.Path(args.root)
    await vault_rag.search_vault(
        root_dir, args.query, top_k=args.limit, project_root=ROOT_DIR
    )


def handle_create(args, vault_models, vault_hydration):
    root_dir = pathlib.Path(args.root)
    doc_type = vault_models.DocType(args.type)
    feature = args.feature.strip("#")
    date_str = datetime.now().strftime("%Y-%m-%d")

    template_path = vault_hydration.get_template_path(ROOT_DIR, doc_type)
    if template_path is None:
        print(f"Error: No template found for type '{doc_type.value}'")
        sys.exit(1)

    content = template_path.read_text(encoding="utf-8")
    hydrated = vault_hydration.hydrate_template(content, feature, date_str, args.title)

    # Generate filename: yyyy-mm-dd-<feature>-<type>.md
    filename = f"{date_str}-{feature}-{doc_type.value}.md"
    target_dir = root_dir / ".docs" / doc_type.value
    target_path = target_dir / filename

    if target_path.exists():
        print(f"Error: File already exists at {target_path}")
        sys.exit(1)

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(hydrated, encoding="utf-8")
    print(f"Created {target_path}")


def handle_audit(args, metrics_api, verification_api, graph_api, vault_models):
    root_dir = pathlib.Path(args.root)
    results = {}

    if args.summary:
        metrics = metrics_api.get_vault_metrics(root_dir)
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
        features = verification_api.list_features(root_dir)
        results["features"] = sorted(features)
        if not args.json:
            print(f"Features ({len(features)}):")
            for f in results["features"]:
                print(f"  - {f}")
            print()

    if args.verify:
        errors = verification_api.get_malformed(root_dir)
        errors.extend(verification_api.verify_vertical_integrity(root_dir))

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

    if args.graph:
        graph = graph_api.VaultGraph(root_dir)
        doc_type_filter = vault_models.DocType(args.type) if args.type else None

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


if __name__ == "__main__":
    main()
