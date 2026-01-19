from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
from pathlib import Path

from app.parsers import WeChatParser, StaticParser, DynamicParser
from app.pdf_generator import PDFGenerator

app = FastAPI(
    title="Link2Context API",
    description="Convert web pages to clean Markdown for LLMs",
    version="2.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache directory
CACHE_DIR = Path(__file__).parent / "cache" / "images"


class ConvertRequest(BaseModel):
    url: str


class MediaInfoResponse(BaseModel):
    images: Dict[str, str] = {}
    videos: List[dict] = []


class ConvertResponse(BaseModel):
    status: str
    title: Optional[str] = None
    markdown: Optional[str] = None
    markdown_with_images: Optional[str] = None
    strategy_used: Optional[str] = None
    media: Optional[MediaInfoResponse] = None
    error: Optional[str] = None


class PDFRequest(BaseModel):
    markdown: str
    title: str = "Document"


# Initialize parsers
wechat_parser = WeChatParser()
static_parser = StaticParser()
dynamic_parser = DynamicParser()
pdf_generator = PDFGenerator()


@app.get("/")
def root():
    return {"message": "Link2Context API", "status": "running", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/convert", response_model=ConvertResponse)
def convert_url(request: ConvertRequest):
    """
    Convert a URL to clean Markdown content with images and videos.
    Uses Strategy Dispatcher pattern with priority order.
    """
    url = request.url.strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Strategy A: WeChat Special Handling
    if wechat_parser.can_handle(url):
        result = wechat_parser.parse(url)
        if result.success:
            media_info = None
            if result.media:
                media_info = MediaInfoResponse(
                    images=result.media.images,
                    videos=result.media.videos
                )
            return ConvertResponse(
                status="success",
                title=result.title,
                markdown=result.markdown,
                markdown_with_images=result.markdown_with_local_images,
                strategy_used="wechat_special",
                media=media_info
            )

    # Strategy B: General Static Parser
    result = static_parser.parse(url)
    if result.success:
        media_info = None
        if result.media:
            media_info = MediaInfoResponse(
                images=result.media.images,
                videos=result.media.videos
            )
        return ConvertResponse(
            status="success",
            title=result.title,
            markdown=result.markdown,
            markdown_with_images=result.markdown_with_local_images,
            strategy_used="static",
            media=media_info
        )

    # Strategy C: Dynamic Fallback (Playwright)
    result = dynamic_parser.parse(url)
    if result.success:
        media_info = None
        if result.media:
            media_info = MediaInfoResponse(
                images=result.media.images,
                videos=result.media.videos
            )
        return ConvertResponse(
            status="success",
            title=result.title,
            markdown=result.markdown,
            markdown_with_images=result.markdown_with_local_images,
            strategy_used="dynamic",
            media=media_info
        )

    # All strategies failed
    return ConvertResponse(
        status="error",
        error=result.error or "Failed to extract content from URL"
    )


@app.get("/api/images/{filename}")
def get_image(filename: str):
    """Serve cached images"""
    image_path = CACHE_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Determine content type
    suffix = image_path.suffix.lower()
    content_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.bmp': 'image/bmp',
    }
    content_type = content_types.get(suffix, 'application/octet-stream')
    
    return FileResponse(image_path, media_type=content_type)


@app.post("/api/generate-pdf")
def generate_pdf(request: PDFRequest):
    """Generate PDF from markdown content"""
    try:
        pdf_bytes = pdf_generator.generate_pdf(request.markdown, request.title)
        
        # Create safe filename for Content-Disposition header
        # Use URL encoding for non-ASCII characters (RFC 5987)
        import urllib.parse
        safe_title = urllib.parse.quote(request.title, safe='')
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_title}.pdf"
            }
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"PDF generation not available: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
