from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
from pathlib import Path

from app.parsers import WeChatParser, StaticParser, DynamicParser
from app.pdf_generator import PDFGenerator
from app.ocr_service import OCRService, OCRConfig
from app.site_analyzer import SiteAnalyzer, AnalyzerConfig
from app.batch_crawler import BatchCrawler

app = FastAPI(
    title="Link2Context API",
    description="Convert web pages to clean Markdown for LLMs",
    version="3.0.0"
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


class OCRConfigRequest(BaseModel):
    provider: str = "openai"  # openai, claude, custom
    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4o"
    prompt: Optional[str] = None


class OCRRequest(BaseModel):
    image_paths: List[str]
    config: OCRConfigRequest


class OCRResultItem(BaseModel):
    success: bool
    image_path: str
    text: Optional[str] = None
    error: Optional[str] = None


class OCRResponse(BaseModel):
    status: str
    results: List[OCRResultItem] = []
    error: Optional[str] = None


# Site crawl models
class AnalyzerConfigRequest(BaseModel):
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    prompt: Optional[str] = None


class AnalyzeSiteRequest(BaseModel):
    url: str
    config: AnalyzerConfigRequest


class PageInfo(BaseModel):
    url: str
    title: str


class AnalyzeSiteResponse(BaseModel):
    status: str
    pages: List[PageInfo] = []
    error: Optional[str] = None


class CrawlSiteRequest(BaseModel):
    pages: List[PageInfo]
    max_pages: int = 50


class CrawledPage(BaseModel):
    url: str
    title: str
    filename: str
    success: bool
    error: Optional[str] = None


class CrawlSiteResponse(BaseModel):
    status: str
    pages: List[CrawledPage] = []
    error: Optional[str] = None


class DownloadRequest(BaseModel):
    pages: List[PageInfo]
    max_pages: int = 50
    format: str = "zip"  # zip or merged


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


@app.post("/api/ocr", response_model=OCRResponse)
async def recognize_images(request: OCRRequest):
    """Recognize text in images using AI vision models"""
    try:
        config = OCRConfig(
            provider=request.config.provider,
            base_url=request.config.base_url,
            api_key=request.config.api_key,
            model=request.config.model,
            prompt=request.config.prompt or ""
        )
        
        ocr_service = OCRService(config)
        results = await ocr_service.recognize_images(request.image_paths)
        
        return OCRResponse(
            status="success",
            results=[
                OCRResultItem(
                    success=r.success,
                    image_path=r.image_path,
                    text=r.text,
                    error=r.error
                ) for r in results
            ]
        )
    except Exception as e:
        return OCRResponse(
            status="error",
            error=str(e)
        )


@app.post("/api/analyze-site", response_model=AnalyzeSiteResponse)
async def analyze_site(request: AnalyzeSiteRequest):
    """Analyze a website to discover documentation pages"""
    try:
        config = AnalyzerConfig(
            provider=request.config.provider,
            base_url=request.config.base_url,
            api_key=request.config.api_key,
            model=request.config.model,
            prompt=request.config.prompt or ""
        )
        
        analyzer = SiteAnalyzer(config)
        result = await analyzer.analyze(request.url)
        
        if result.success:
            return AnalyzeSiteResponse(
                status="success",
                pages=[PageInfo(url=p['url'], title=p['title']) for p in result.pages]
            )
        else:
            return AnalyzeSiteResponse(
                status="error",
                error=result.error
            )
    except Exception as e:
        return AnalyzeSiteResponse(
            status="error",
            error=str(e)
        )


@app.post("/api/crawl-site", response_model=CrawlSiteResponse)
def crawl_site(request: CrawlSiteRequest):
    """Crawl multiple pages from a site"""
    try:
        crawler = BatchCrawler()
        pages_dict = [{"url": p.url, "title": p.title} for p in request.pages]
        results = crawler.crawl_batch_sync(pages_dict, request.max_pages)
        
        return CrawlSiteResponse(
            status="success",
            pages=[
                CrawledPage(
                    url=r.url,
                    title=r.title,
                    filename=r.filename,
                    success=r.success,
                    error=r.error
                ) for r in results
            ]
        )
    except Exception as e:
        return CrawlSiteResponse(
            status="error",
            error=str(e)
        )


@app.post("/api/download-site")
def download_site(request: DownloadRequest):
    """Download crawled site as ZIP or merged markdown"""
    try:
        import urllib.parse
        
        crawler = BatchCrawler()
        pages_dict = [{"url": p.url, "title": p.title} for p in request.pages]
        results = crawler.crawl_batch_sync(pages_dict, request.max_pages)
        
        if request.format == "merged":
            # Merge into single markdown
            merged_content = crawler.merge_markdown(results)
            return Response(
                content=merged_content.encode('utf-8'),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''complete_docs.md"
                }
            )
        else:
            # Create ZIP
            zip_bytes = crawler.create_zip(results)
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''docs.zip"
                }
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
