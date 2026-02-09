from __future__ import annotations

import json
import logging
import pathlib

from vault.parser import (
    parse_vault_metadata,
)
from vault.scanner import (
    scan_vault,
)

from orchestration.dispatch import (
    run_dispatch,
)

logger = logging.getLogger(__name__)


class DocSignature:
    def __init__(
        self,
        path: str,
        signature: str,
        feature: str,
        doc_type: str,
        tags: list[str],
    ):
        self.path = path
        self.signature = signature
        self.feature = feature
        self.doc_type = doc_type
        self.tags = tags


class VaultIndex:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.index_path = root_dir / ".rules" / "vault_index.json"
        self.signatures: dict[str, DocSignature] = {}
        self._load()

    def _load(self):
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            for path, sig_data in data.items():
                self.signatures[path] = DocSignature(**sig_data)
        except Exception as e:
            logger.error(f"Failed to load vault index: {e}")

    def save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {path: sig.__dict__ for path, sig in self.signatures.items()}
        self.index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def generate_signature(
    content: str,
    root_dir: pathlib.Path,
    project_root: pathlib.Path | None = None,
) -> str:
    """Uses sophisticated dispatch fallback to generate a dense semantic signature."""
    prompt = (
        "Generate a dense, 50-word 'Semantic Signature' for the following "
        "technical document. "
        "Include core concepts, technologies, key decisions, and unique identifiers. "
        "Do not include preamble. Output ONLY the signature.\n\n"
        f"Document Content:\n{content}"
    )

    # Use project_root for agent loading if provided, else root_dir
    agent_root = project_root or root_dir

    try:
        # Using a standard-executor agent or similar.
        # This will follow the Gemini/Claude fallback chain automatically.
        result = await run_dispatch(
            agent_name="standard-executor",
            root_dir=agent_root,
            initial_task=prompt,
            quiet=True,
        )
        return result.response_text.strip()
    except Exception as e:
        logger.error(f"Signature generation dispatch failed: {e}")
        return ""


async def index_vault(
    root_dir: pathlib.Path,
    force: bool = False,
    project_root: pathlib.Path | None = None,
    limit: int | None = None,
):
    """Updates the vault index with new or changed documents."""
    index = VaultIndex(root_dir)
    print(f"Indexing vault at {root_dir}...")

    all_docs = list(scan_vault(root_dir))
    updated_count = 0

    docs_to_index = []
    for doc_path in all_docs:
        rel_path = str(doc_path.relative_to(root_dir))
        if force or rel_path not in index.signatures:
            docs_to_index.append(doc_path)

    if limit:
        docs_to_index = docs_to_index[:limit]

    for doc_path in docs_to_index:
        rel_path = str(doc_path.relative_to(root_dir))
        print(f"  Indexing {rel_path}...")
        try:
            content = doc_path.read_text(encoding="utf-8")
            meta, _ = parse_vault_metadata(content)

            tags_to_ignore = {
                "#adr",
                "#exec",
                "#plan",
                "#reference",
                "#research",
            }
            feature_tags = [t.lstrip("#") for t in meta.tags if t not in tags_to_ignore]
            feature = feature_tags[0] if feature_tags else "unknown"

            signature = await generate_signature(
                content, root_dir, project_root=project_root
            )
            if signature:
                index.signatures[rel_path] = DocSignature(
                    path=rel_path,
                    signature=signature,
                    feature=feature,
                    doc_type=pathlib.Path(rel_path).parent.name,
                    tags=meta.tags,
                )
                updated_count += 1
        except Exception as e:
            print(f"    Failed to index {rel_path}: {e}")

    if updated_count > 0:
        index.save()
        print(f"Index updated. {updated_count} documents added/updated.")
    else:
        print("Index is up to date.")


async def rank_documents(
    query: str,
    signatures: list[DocSignature],
    root_dir: pathlib.Path,
    top_k: int = 5,
    project_root: pathlib.Path | None = None,
) -> list[tuple[DocSignature, float]]:
    """Ranks documents by relevance to the query using an LLM."""
    if not signatures:
        return []

    sig_text = "\n".join([f"- {s.path}: {s.signature}" for s in signatures])
    prompt = (
        f"Query: {query}\n\n"
        f"Identify and rank the top {top_k} documents from the following list "
        "that are most relevant to the query. "
        "Return the result as a JSON list of objects with 'id' and "
        "'relevance_score' (0.0 to 1.0). "
        "Output ONLY the JSON.\n\n"
        f"Documents:\n{sig_text}"
    )

    agent_root = project_root or root_dir

    try:
        result = await run_dispatch(
            agent_name="standard-executor",
            root_dir=agent_root,
            initial_task=prompt,
            quiet=True,
        )
        data = json.loads(result.response_text.strip())
        ranked = []
        for item in data:
            doc_id = item["id"]
            score = item["relevance_score"]
            # Find the signature
            for s in signatures:
                if s.path == doc_id:
                    ranked.append((s, score))
                    break
        return sorted(ranked, key=lambda x: x[1], reverse=True)[:top_k]
    except Exception as e:
        logger.error(f"Ranking documents failed: {e}")
        return []


async def search_vault(
    root_dir: pathlib.Path,
    query: str,
    top_k: int = 5,
    project_root: pathlib.Path | None = None,
):
    """Performs semantic search across the vault index."""
    index = VaultIndex(root_dir)
    if not index.signatures:
        print("Vault index is empty. Run indexing first.")
        return []

    sigs = list(index.signatures.values())
    results = await rank_documents(
        query, sigs, root_dir, top_k, project_root=project_root
    )

    if not results:
        print("No relevant documents found.")
        return []

    print(f"Search results for '{query}':")
    for sig, score in results:
        print(f"  [{score:.2f}] {sig.path} (#{sig.feature})")
        snippet = (
            sig.signature[:100] + "..." if len(sig.signature) > 100 else sig.signature
        )
        print(f"    {snippet}")

    return results
