"""PDF/Document → Markdown conversion using Marker.

Marker is the strongest open-source PDF parser — handles tables, formulas,
multi-column layouts, and scanned documents far better than PyMuPDF.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


async def pdf_to_markdown(url_or_path: str) -> str:
    """Convert a PDF to markdown using Marker.

    Args:
        url_or_path: URL to a PDF file, or local file path.

    Returns:
        JSON string with 'success', 'markdown', 'metadata'.
    """
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        # Download if URL
        local_path = url_or_path
        tmp_file = None
        if url_or_path.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url_or_path)
                resp.raise_for_status()
                tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp_file.write(resp.content)
                tmp_file.close()
                local_path = tmp_file.name

        # Convert
        converter = PdfConverter(artifact_dict=create_model_dict())
        result = converter(local_path)

        markdown = result.markdown
        metadata = {
            "pages": len(result.pages) if hasattr(result, "pages") else 0,
            "source": url_or_path,
        }

        # Cleanup
        if tmp_file:
            os.unlink(tmp_file.name)

        return json.dumps({
            "success": True,
            "markdown": markdown,
            "metadata": metadata,
            "length": len(markdown),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("Marker PDF conversion failed: %s", e)
        return json.dumps({
            "success": False,
            "error": str(e),
            "markdown": "",
        }, ensure_ascii=False)


def check_marker() -> bool:
    try:
        from marker.converters.pdf import PdfConverter  # noqa: F401
        return True
    except ImportError:
        return False


# ─── Tool Registration ────────────────────────────────────────────────────────

from tools.registry import registry

PDF_CONVERT_SCHEMA = {
    "name": "pdf_to_markdown",
    "description": (
        "Convert a PDF document to high-quality markdown. Handles tables, formulas, "
        "multi-column layouts, and scanned documents. Accepts a URL to a PDF or a "
        "local file path. Use this for arxiv papers, financial reports, contracts, "
        "and any complex PDF that web_extract can't handle well."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url_or_path": {
                "type": "string",
                "description": "URL to a PDF file (e.g. https://arxiv.org/pdf/...) or local file path.",
            },
        },
        "required": ["url_or_path"],
    },
}

registry.register(
    name="pdf_to_markdown",
    toolset="web",
    schema=PDF_CONVERT_SCHEMA,
    handler=lambda args, **kw: pdf_to_markdown(args.get("url_or_path", "")),
    check_fn=check_marker,
    is_async=True,
    emoji="📑",
    max_result_size_chars=500_000,
)
