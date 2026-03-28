#!/usr/bin/env python3
"""
link2context MCP Server - Streamable HTTP via StreamableHTTPSessionManager
"""
import sys, os, json, asyncio, logging
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("mcp_server")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

server_instance = Server(name="link2context-mcp")

@server_instance.list_tools()
async def list_tools():
    return [
        Tool(
            name="convert_page",
            description="Convert a URL to clean Markdown. Supports static HTML, JS-rendered pages (Next.js, VitePress), WeChat.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to convert"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="crawl_site",
            description="Crawl an entire website, converting all pages to Markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Root URL of site to crawl"},
                    "max_pages": {"type": "integer", "description": "Max pages (default 10, max 50)"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="ocr_image",
            description="AI OCR on an image URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "Image URL to OCR"},
                    "language": {"type": "string", "description": "Language: zh-CN, en, or auto"},
                },
                "required": ["image_url"],
            },
        ),
    ]

@server_instance.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]):
    try:
        import httpx
        ssl_cert = os.environ.get("REQUESTS_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            if name == "convert_page":
                url = arguments["url"]
                resp = await client.post(
                    f"{BACKEND_URL}/api/convert",
                    json={"url": url},
                    headers={"Content-Type": "application/json"},
                    verify=ssl_cert,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"# {data.get('title','Untitled')}\n\n{data.get('markdown','')}"
                    )]
                return [TextContent(type="text", text=f"Error: {data.get('error','Unknown')}")]
            
            elif name == "crawl_site":
                url = arguments["url"]
                max_pages = min(int(arguments.get("max_pages", 10)), 50)
                
                analyze_resp = await client.post(
                    f"{BACKEND_URL}/api/analyze-site",
                    json={"url": url},
                    headers={"Content-Type": "application/json"},
                    verify=ssl_cert,
                )
                analyze_resp.raise_for_status()
                pages = analyze_resp.json().get("pages", [])[:max_pages]
                
                results = []
                for page in pages:
                    page_url = page.get("url", "")
                    if not page_url:
                        continue
                    try:
                        conv_resp = await client.post(
                            f"{BACKEND_URL}/api/convert",
                            json={"url": page_url},
                            headers={"Content-Type": "application/json"},
                            verify=ssl_cert,
                        )
                        conv_resp.raise_for_status()
                        d = conv_resp.json()
                        results.append({
                            "url": page_url,
                            "title": d.get("title", ""),
                            "markdown": d.get("markdown", ""),
                            "success": d.get("status") == "success",
                            "error": d.get("error"),
                        })
                    except Exception as e:
                        results.append({"url": page_url, "success": False, "error": str(e)})
                
                return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]
            
            elif name == "ocr_image":
                image_url = arguments["image_url"]
                language = arguments.get("language", "auto")
                resp = await client.post(
                    f"{BACKEND_URL}/api/ocr",
                    json={"image_url": image_url, "language": language},
                    headers={"Content-Type": "application/json"},
                    verify=ssl_cert,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    return [TextContent(type="text", text=data.get("text", ""))]
                return [TextContent(type="text", text=f"Error: {data.get('error','Unknown')}")]
        
    except Exception as e:
        logger.error(f"[call_tool] {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

# ─── Streamable HTTP Session Manager ─────────────────────────────────────────
import uvicorn

session_manager = StreamableHTTPSessionManager(
    app=server_instance,
    stateless=True,
    json_response=True,
)

async def main():
    logger.info("=" * 60)
    logger.info("link2context MCP Server")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info(f"REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', '/etc/ssl/certs/ca-certificates.crt')}")
    logger.info("=" * 60)
    
    config = uvicorn.Config(
        session_manager.handle_request,
        host="0.0.0.0",
        port=8001,
        log_level="info",
        interface="asgi3",
    )
    
    async with session_manager.run():
        # session_manager task group is active; now serve
        await uvicorn.Server(config).serve()

if __name__ == "__main__":
    asyncio.run(main())
