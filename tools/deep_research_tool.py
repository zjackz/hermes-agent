"""Deep Research tool powered by GPT-Researcher.

Provides autonomous multi-source research that generates comprehensive
reports with citations. Replaces the manual search→extract→synthesize workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


async def deep_research(
    query: str,
    report_type: str = "research_report",
    max_subtopics: int = 3,
    tone: str = "informative",
) -> str:
    """Conduct autonomous deep research on a topic.

    Args:
        query: Research question or topic.
        report_type: One of 'research_report', 'detailed_report', 'quick_report'.
        max_subtopics: Max sub-questions to explore (1-5).
        tone: Report tone ('objective', 'informative', 'analytical').

    Returns:
        JSON string with 'report' (markdown), 'sources', 'costs'.
    """
    from gpt_researcher import GPTResearcher
    from gpt_researcher.utils.enum import Tone

    # Map tone string
    tone_map = {
        "objective": Tone.Objective,
        "informative": Tone.Informative,
        "analytical": Tone.Analytical,
    }
    selected_tone = tone_map.get(tone, Tone.Informative)

    # Configure via env vars (GPT-Researcher reads these)
    # Use OpenRouter as the LLM backend
    if not os.environ.get("OPENAI_API_KEY"):
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if openrouter_key:
            os.environ["OPENAI_API_KEY"] = openrouter_key
            os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
            if not os.environ.get("FAST_LLM"):
                os.environ["FAST_LLM"] = "openai:openai/gpt-4o-mini"
            if not os.environ.get("SMART_LLM"):
                os.environ["SMART_LLM"] = "openai:openai/gpt-4o-mini"

    # Use Tavily for search if available, otherwise DuckDuckGo
    if os.environ.get("TAVILY_API_KEY") and not os.environ.get("RETRIEVER"):
        os.environ["RETRIEVER"] = "tavily"
    elif not os.environ.get("RETRIEVER"):
        os.environ["RETRIEVER"] = "duckduckgo"

    try:
        researcher = GPTResearcher(
            query=query,
            report_type=report_type,
            tone=selected_tone,
            max_subtopics=max(1, min(max_subtopics, 5)),
            verbose=False,
        )

        report = await researcher.conduct_research()
        sources = researcher.get_source_urls()
        costs = researcher.get_costs() if hasattr(researcher, "get_costs") else 0

        return json.dumps({
            "success": True,
            "report": report,
            "sources": sources,
            "sources_count": len(sources),
            "costs": costs,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("Deep research failed: %s", e)
        return json.dumps({
            "success": False,
            "error": str(e),
            "report": "",
            "sources": [],
        }, ensure_ascii=False)


def check_deep_research() -> bool:
    """Check if deep research is available."""
    try:
        from gpt_researcher import GPTResearcher  # noqa: F401
        return bool(
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
        )
    except ImportError:
        return False


# ─── Tool Registration ────────────────────────────────────────────────────────

from tools.registry import registry

DEEP_RESEARCH_SCHEMA = {
    "name": "deep_research",
    "description": (
        "Conduct autonomous deep research on any topic. Generates a comprehensive "
        "markdown report with citations by automatically searching multiple sources, "
        "cross-referencing information, and synthesizing findings. "
        "Use this instead of multiple web_search + web_extract calls when you need "
        "thorough research on a complex topic. Takes 1-3 minutes to complete."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The research question or topic to investigate deeply.",
            },
            "report_type": {
                "type": "string",
                "enum": ["research_report", "detailed_report", "quick_report"],
                "description": "Report depth: quick_report (30s), research_report (1-2min), detailed_report (2-3min).",
                "default": "research_report",
            },
        },
        "required": ["query"],
    },
}

registry.register(
    name="deep_research",
    toolset="web",
    schema=DEEP_RESEARCH_SCHEMA,
    handler=lambda args, **kw: deep_research(
        args.get("query", ""),
        report_type=args.get("report_type", "research_report"),
    ),
    check_fn=check_deep_research,
    is_async=True,
    emoji="🔬",
    max_result_size_chars=200_000,
)
