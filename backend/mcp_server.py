#!/usr/bin/env python3
"""
link2context MCP Server
Exposes convert_page, crawl_site, ocr_image tools via MCP Streamable HTTP transport.
Calls the FastAPI backend at http://localhost:8000 internally.
"""

import sys
import os
import json
import asyncio
import logging
from typing import Any, Optional

# Setup logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("mcp_server")

# MCP error codes
ERR_INVALID_PARAMS = -32602
ERR_TIMEOUT = -32001
ERR_UNREACHABLE = -32002
ERR_EMPTY_CONTENT = -32003

# Backend URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# Import MCP - try official package first, fallback to fastmcp
try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
    logger.info("Using mcp.server.fastmcp")
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp.server.fastmcp not available, will use fallback")


def _build_error_response(code: int, message: str, data: Any = None) -> dict:
    """Build a JSONRPC error response."""
    resp = {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        resp["error"]["data"] = data
    return resp


def _build_success_response(result: Any, request_id: Any = None) -> dict:
    """Build a JSONRPC success response."""
    resp = {
        "jsonrpc": "2.0",
        "result": result,
    }
    if request_id is not None:
        resp["id"] = request_id
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool Implementations
# ─────────────────────────────────────────────────────────────────────────────

async def convert_page(url: str, request_id: Any = None) -> dict:
    """
    Convert a URL to clean Markdown content.
    Calls POST /api/convert on the FastAPI backend.
    """
    logger.info(f"[convert_page] URL: {url}")

    if not url or not isinstance(url, str):
        logger.warning("[convert_page] Invalid params: url is required")
        return _build_error_response(
            ERR_INVALID_PARAMS,
            "Invalid params: url is required and must be a string",
            request_id=request_id,
        )

    url = url.strip()

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/convert",
                json={"url": url},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                logger.info(
                    f"[convert_page] Success: {data.get('title', 'no title')} "
                    f"({len(data.get('markdown', ''))} chars)"
                )
                return _build_success_response(
                    {
                        "title": data.get("title"),
                        "markdown": data.get("markdown"),
                        "markdown_with_images": data.get("markdown_with_images"),
                        "strategy_used": data.get("strategy_used"),
                        "media": data.get("media"),
                    },
                    request_id=request_id,
                )
            else:
                error_msg = data.get("error", "Unknown error")
                logger.warning(f"[convert_page] Error: {error_msg}")
                return _build_error_response(
                    ERR_EMPTY_CONTENT,
                    f"Conversion failed: {error_msg}",
                    request_id=request_id,
                )

    except httpx.TimeoutException:
        logger.warning(f"[convert_page] Timeout for URL: {url}")
        return _build_error_response(
            ERR_TIMEOUT,
            f"Request timed out after 60s for URL: {url}",
            request_id=request_id,
        )
    except httpx.ConnectError:
        logger.error(f"[convert_page] Cannot connect to backend at {BACKEND_URL}")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Backend unreachable at {BACKEND_URL}. Is the API service running?",
            request_id=request_id,
        )
    except Exception as e:
        logger.exception(f"[convert_page] Unexpected error for URL: {url}")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Unexpected error: {str(e)}",
            request_id=request_id,
        )


async def crawl_site(
    pages: list,
    max_pages: int = 50,
    request_id: Any = None,
) -> dict:
    """
    Crawl multiple pages from a site.
    Calls POST /api/crawl-site on the FastAPI backend.
    """
    logger.info(f"[crawl_site] pages={len(pages)}, max_pages={max_pages}")

    if not pages or not isinstance(pages, list):
        logger.warning("[crawl_site] Invalid params: pages must be a non-empty list")
        return _build_error_response(
            ERR_INVALID_PARAMS,
            "Invalid params: pages must be a non-empty list of {url, title} objects",
            request_id=request_id,
        )

    if max_pages <= 0:
        max_pages = 50

    try:
        import httpx

        pages_payload = [
            {"url": p.get("url") or p.get("url"), "title": p.get("title", "")}
            for p in pages
        ]

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/crawl-site",
                json={"pages": pages_payload, "max_pages": max_pages},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                success_count = len([p for p in data.get("pages", []) if p.get("success")])
                logger.info(f"[crawl_site] Success: {success_count}/{len(pages_payload)} pages")
                return _build_success_response(
                    {
                        "pages": data.get("pages", []),
                        "total": len(pages_payload),
                        "success_count": success_count,
                    },
                    request_id=request_id,
                )
            else:
                error_msg = data.get("error", "Unknown error")
                logger.warning(f"[crawl_site] Error: {error_msg}")
                return _build_error_response(
                    ERR_EMPTY_CONTENT,
                    f"Crawl failed: {error_msg}",
                    request_id=request_id,
                )

    except httpx.TimeoutException:
        logger.warning("[crawl_site] Timeout after 300s")
        return _build_error_response(
            ERR_TIMEOUT,
            "Request timed out after 300s",
            request_id=request_id,
        )
    except httpx.ConnectError:
        logger.error(f"[crawl_site] Cannot connect to backend at {BACKEND_URL}")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Backend unreachable at {BACKEND_URL}. Is the API service running?",
            request_id=request_id,
        )
    except Exception as e:
        logger.exception("[crawl_site] Unexpected error")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Unexpected error: {str(e)}",
            request_id=request_id,
        )


async def ocr_image(
    image_paths: list,
    api_key: str,
    provider: str = "openai",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o",
    prompt: Optional[str] = None,
    request_id: Any = None,
) -> dict:
    """
    Recognize text in images using AI vision models.
    Calls POST /api/ocr on the FastAPI backend.
    """
    logger.info(f"[ocr_image] images={len(image_paths)}, provider={provider}")

    if not image_paths or not isinstance(image_paths, list):
        logger.warning("[ocr_image] Invalid params: image_paths must be a non-empty list")
        return _build_error_response(
            ERR_INVALID_PARAMS,
            "Invalid params: image_paths must be a non-empty list of image paths",
            request_id=request_id,
        )

    if not api_key:
        logger.warning("[ocr_image] Invalid params: api_key is required")
        return _build_error_response(
            ERR_INVALID_PARAMS,
            "Invalid params: api_key is required",
            request_id=request_id,
        )

    default_prompt = (
        "请识别这张图片中的所有文字内容。保持原有的格式和结构，"
        "如果有标题、列表、表格等，请用Markdown格式输出。"
    )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/ocr",
                json={
                    "image_paths": image_paths,
                    "config": {
                        "provider": provider,
                        "base_url": base_url,
                        "api_key": api_key,
                        "model": model,
                        "prompt": prompt or default_prompt,
                    },
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                success_count = len([r for r in data.get("results", []) if r.get("success")])
                logger.info(f"[ocr_image] Success: {success_count}/{len(image_paths)} images")
                return _build_success_response(
                    {
                        "results": data.get("results", []),
                        "total": len(image_paths),
                        "success_count": success_count,
                    },
                    request_id=request_id,
                )
            else:
                error_msg = data.get("error", "Unknown error")
                logger.warning(f"[ocr_image] Error: {error_msg}")
                return _build_error_response(
                    ERR_EMPTY_CONTENT,
                    f"OCR failed: {error_msg}",
                    request_id=request_id,
                )

    except httpx.TimeoutException:
        logger.warning("[ocr_image] Timeout after 120s")
        return _build_error_response(
            ERR_TIMEOUT,
            "Request timed out after 120s",
            request_id=request_id,
        )
    except httpx.ConnectError:
        logger.error(f"[ocr_image] Cannot connect to backend at {BACKEND_URL}")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Backend unreachable at {BACKEND_URL}. Is the API service running?",
            request_id=request_id,
        )
    except Exception as e:
        logger.exception("[ocr_image] Unexpected error")
        return _build_error_response(
            ERR_UNREACHABLE,
            f"Unexpected error: {str(e)}",
            request_id=request_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server (Streamable HTTP Transport)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "convert_page",
        "description": "Convert a single URL to clean Markdown content with images and videos. "
        "Returns title, markdown, markdown_with_images, strategy_used, and media info.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to convert to Markdown",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "crawl_site",
        "description": "Crawl multiple pages from a website and return their Markdown content. "
        "Each page result includes url, title, filename, success status, and markdown content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pages": {
                    "type": "array",
                    "description": "List of pages to crawl, each with url and title",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["url"],
                    },
                },
                "max_pages": {
                    "type": "integer",
                    "description": "Maximum number of pages to crawl (default: 50)",
                    "default": 50,
                },
            },
            "required": ["pages"],
        },
    },
    {
        "name": "ocr_image",
        "description": "Recognize and extract text from images using AI vision models (OpenAI GPT-4o or Claude). "
        "Returns the recognized text for each image.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_paths": {
                    "type": "array",
                    "description": "List of image file paths or URLs to process",
                    "items": {"type": "string"},
                },
                "api_key": {
                    "type": "string",
                    "description": "API key for the vision model provider",
                },
                "provider": {
                    "type": "string",
                    "description": "Provider: openai or claude (default: openai)",
                    "default": "openai",
                },
                "base_url": {
                    "type": "string",
                    "description": "Base URL for the API (default: https://api.openai.com/v1)",
                    "default": "https://api.openai.com/v1",
                },
                "model": {
                    "type": "string",
                    "description": "Vision model name (default: gpt-4o)",
                    "default": "gpt-4o",
                },
                "prompt": {
                    "type": "string",
                    "description": "Custom prompt for text recognition",
                },
            },
            "required": ["image_paths", "api_key"],
        },
    },
]


async def handle_mcp_request(request_body: dict) -> dict:
    """Handle an incoming MCP JSONRPC request."""
    method = request_body.get("method", "")
    request_id = request_body.get("id")
    params = request_body.get("params", {})

    logger.info(f"[MCP Request] method={method}, id={request_id}")

    # ── tools/list ──────────────────────────────────────────────────────────
    if method == "tools/list":
        return _build_success_response({"tools": TOOL_DEFINITIONS}, request_id=request_id)

    # ── tools/call ─────────────────────────────────────────────────────────
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name == "convert_page":
            return await convert_page(
                url=tool_args.get("url", ""),
                request_id=request_id,
            )
        elif tool_name == "crawl_site":
            return await crawl_site(
                pages=tool_args.get("pages", []),
                max_pages=tool_args.get("max_pages", 50),
                request_id=request_id,
            )
        elif tool_name == "ocr_image":
            return await ocr_image(
                image_paths=tool_args.get("image_paths", []),
                api_key=tool_args.get("api_key", ""),
                provider=tool_args.get("provider", "openai"),
                base_url=tool_args.get("base_url", "https://api.openai.com/v1"),
                model=tool_args.get("model", "gpt-4o"),
                prompt=tool_args.get("prompt"),
                request_id=request_id,
            )
        else:
            return _build_error_response(
                ERR_INVALID_PARAMS,
                f"Unknown tool: {tool_name}",
                request_id=request_id,
            )

    # ── Other methods ────────────────────────────────────────────────────────
    if method == "initialize":
        return _build_success_response(
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "link2context-mcp",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                },
            },
            request_id=request_id,
        )

    if method == "ping":
        return _build_success_response({"status": "pong"}, request_id=request_id)

    # Not found
    return _build_error_response(
        ERR_INVALID_PARAMS,
        f"Method not found: {method}",
        request_id=request_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Streamable HTTP Server
# ─────────────────────────────────────────────────────────────────────────────

async def streamable_http_handler(scope, receive, send):
    """Handle incoming HTTP requests with Streamable HTTP transport."""
    import json

    # Read request body
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        if message["type"] == "http.request":
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

    # Parse JSONRPC request
    try:
        request_body = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [[b"content-type", b"application/json"]],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
                ).encode("utf-8"),
            }
        )
        return

    # Handle the request
    try:
        response_body = await handle_mcp_request(request_body)
    except Exception as e:
        logger.exception("[MCP] Unhandled exception")
        response_body = _build_error_response(
            ERR_UNREACHABLE,
            f"Internal server error: {str(e)}",
            request_id=request_body.get("id"),
        )

    # Send HTTP response
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"application/json"],
                [b"Cache-Control", b"no-cache"],
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": json.dumps(response_body).encode("utf-8"),
        }
    )


async def run_server(host: str = "0.0.0.0", port: int = 8001):
    """Run the MCP server using ASGI/UVicorn with Streamable HTTP."""
    import uvicorn
    from starlette.routing import Mount

    # Mount the ASGI app directly - no Starlette routing needed
    app = streamable_http_handler

    logger.info(f"Starting link2context MCP server on {host}:{port}")
    logger.info(f"Backend URL: {BACKEND_URL}")
    logger.info(f"REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', 'not set')}")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main():
    port = int(os.environ.get("MCP_PORT", "8001"))
    host = os.environ.get("MCP_HOST", "0.0.0.0")

    logger.info("=" * 60)
    logger.info("link2context MCP Server v1.0.0")
    logger.info(f"Port: {port}, Host: {host}")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info("=" * 60)

    try:
        asyncio.run(run_server(host=host, port=port))
    except KeyboardInterrupt:
        logger.info("MCP server stopped")
    except Exception as e:
        logger.exception(f"MCP server failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
