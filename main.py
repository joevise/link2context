"""
link2context API - URL to Markdown converter
"""
import os
import asyncio
from functools import partial
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from typing import Optional
from pathlib import Path

from parsers import WeChatParser, StaticParser, DynamicParser
from media_handler import MediaHandler, CACHE_DIR

app = FastAPI(
    title="link2context",
    description="Convert any URL to clean Markdown with image caching and video detection",
    version="1.0.0",
)


class ParseRequest(BaseModel):
    url: str
    use_dynamic: bool = False  # Force Playwright for JS-heavy pages


class ParseResponse(BaseModel):
    success: bool
    title: Optional[str] = None
    markdown: Optional[str] = None
    markdown_with_local_images: Optional[str] = None
    images: Optional[dict] = None
    videos: Optional[list] = None
    error: Optional[str] = None


# Parser chain
parsers = [
    WeChatParser(),
    StaticParser(),
]
dynamic_parser = DynamicParser()


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve frontend"""
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "link2context"}


def _parse_sync(url: str, use_dynamic: bool):
    """Run parsing in a thread to avoid blocking the async event loop"""
    if use_dynamic:
        return dynamic_parser.parse(url)

    result = None
    for parser in parsers:
        if parser.can_handle(url):
            result = parser.parse(url)
            if result.success:
                return result

    # Fallback to dynamic if static failed
    return dynamic_parser.parse(url)


@app.post("/parse", response_model=ParseResponse)
async def parse_url(req: ParseRequest):
    """Parse a URL and return markdown content"""
    url = str(req.url)

    # Run sync parsers in a thread pool to avoid blocking asyncio
    result = await asyncio.to_thread(_parse_sync, url, req.use_dynamic)

    if not result.success:
        return ParseResponse(success=False, error=result.error)

    return ParseResponse(
        success=True,
        title=result.title,
        markdown=result.markdown,
        markdown_with_local_images=result.markdown_with_local_images,
        images=result.media.images if result.media else None,
        videos=result.media.videos if result.media else None,
    )


@app.get("/api/images/{filename}")
async def get_image(filename: str):
    """Serve cached images"""
    filepath = CACHE_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(filepath)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
