"""Semantic memory layer using Mem0 for Hermes agent.

Provides vector-based semantic search over agent memories, complementing
the existing MEMORY.md text-based explicit memory system.

Architecture:
- MEMORY.md = explicit memory (user-readable, substring match)
- Mem0 = implicit memory (auto-extracted, semantic search)
- Query merges both layers: exact match from text, fuzzy from vectors
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_mem0_instance = None
_initialized = False


def _get_hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _get_mem0_config() -> Dict[str, Any]:
    """Build Mem0 config using available API keys."""
    hermes_home = _get_hermes_home()
    db_path = os.path.join(hermes_home, "memories", "mem0_vectors")
    history_path = os.path.join(hermes_home, "memories", "mem0_history.db")

    # Embedder: prefer OpenAI-compatible (via OpenRouter), fallback to huggingface
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    if openai_key:
        embedder_config = {
            "provider": "openai",
            "config": {"api_key": openai_key, "model": "text-embedding-3-small"},
        }
        embedding_dims = 1536
    elif openrouter_key:
        embedder_config = {
            "provider": "openai",
            "config": {
                "api_key": openrouter_key,
                "model": "openai/text-embedding-3-small",
                "openai_base_url": "https://openrouter.ai/api/v1",
            },
        }
        embedding_dims = 1536
    else:
        # Local huggingface (requires sentence-transformers)
        embedder_config = {
            "provider": "huggingface",
            "config": {"model": "all-MiniLM-L6-v2"},
        }
        embedding_dims = 384

    # LLM for memory extraction: use OpenAI-compatible
    if openai_key:
        llm_config = {
            "provider": "openai",
            "config": {"api_key": openai_key, "model": "gpt-4o-mini"},
        }
    elif openrouter_key:
        llm_config = {
            "provider": "openai",
            "config": {
                "api_key": openrouter_key,
                "model": "openai/gpt-4o-mini",
                "openai_base_url": "https://openrouter.ai/api/v1",
            },
        }
    else:
        llm_config = {"provider": "mock", "config": {}}

    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "hermes_memories",
                "path": db_path,
                "embedding_model_dims": embedding_dims,
            },
        },
        "embedder": embedder_config,
        "llm": llm_config,
        "history_db_path": history_path,
        "version": "v1.1",
    }


def get_memory() -> Any:
    """Get or create the Mem0 Memory instance (singleton)."""
    global _mem0_instance, _initialized
    if _mem0_instance is not None:
        return _mem0_instance

    try:
        from mem0 import Memory
        from mem0.configs.base import MemoryConfig

        config = _get_mem0_config()
        os.makedirs(os.path.dirname(config["history_db_path"]), exist_ok=True)
        os.makedirs(config["vector_store"]["config"]["path"], exist_ok=True)

        _mem0_instance = Memory(config=MemoryConfig(**config))
        _initialized = True
        logger.info("Mem0 semantic memory initialized (embedder=%s)", config["embedder"]["provider"])
        return _mem0_instance
    except Exception as e:
        logger.warning("Failed to initialize Mem0: %s", e)
        _initialized = False
        return None


def add_memory(content: str, user_id: str = "hermes", metadata: Optional[Dict] = None) -> Optional[str]:
    """Add a memory to the semantic store.

    Args:
        content: The memory content to store.
        user_id: User identifier (default: "hermes").
        metadata: Optional metadata dict.

    Returns:
        Memory ID if successful, None otherwise.
    """
    mem = get_memory()
    if not mem:
        return None
    try:
        result = mem.add(content, user_id=user_id, metadata=metadata or {})
        # Mem0 v2 returns a dict with 'results' list
        if isinstance(result, dict) and "results" in result:
            results = result["results"]
            if results:
                return results[0].get("id")
        return str(result) if result else None
    except Exception as e:
        logger.warning("Mem0 add failed: %s", e)
        return None


def search_memory(query: str, user_id: str = "hermes", limit: int = 5) -> List[Dict[str, Any]]:
    """Search memories by semantic similarity."""
    mem = get_memory()
    if not mem:
        return []
    try:
        results = mem.search(query, filters={"user_id": user_id}, limit=limit)
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        return [
            {
                "memory": r.get("memory", r.get("text", "")),
                "score": r.get("score", 0),
                "id": r.get("id", ""),
            }
            for r in (results or [])
        ]
    except Exception as e:
        logger.warning("Mem0 search failed: %s", e)
        return []


def get_all_memories(user_id: str = "hermes") -> List[Dict[str, Any]]:
    """Get all stored memories."""
    mem = get_memory()
    if not mem:
        return []
    try:
        results = mem.get_all(filters={"user_id": user_id})
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        return results or []
    except Exception as e:
        logger.warning("Mem0 get_all failed: %s", e)
        return []


def delete_memory(memory_id: str) -> bool:
    """Delete a specific memory by ID."""
    mem = get_memory()
    if not mem:
        return False
    try:
        mem.delete(memory_id)
        return True
    except Exception as e:
        logger.warning("Mem0 delete failed: %s", e)
        return False


def is_available() -> bool:
    """Check if semantic memory is available (has embedder configured)."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    has_local = False
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        has_local = True
    except ImportError:
        pass
    return bool(openai_key or openrouter_key or has_local)
