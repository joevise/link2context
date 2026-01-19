import asyncio
import zipfile
import io
import re
from typing import List, Dict, Optional, AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from app.parsers import StaticParser, DynamicParser


@dataclass
class PageResult:
    url: str
    title: str
    filename: str
    markdown: str
    success: bool
    error: Optional[str] = None


@dataclass
class BatchProgress:
    current: int
    total: int
    current_url: str
    current_title: str
    status: str  # "crawling", "done", "error"


class BatchCrawler:
    """Batch crawl multiple pages and package results"""
    
    def __init__(self):
        self.static_parser = StaticParser()
        self.dynamic_parser = DynamicParser()
    
    def _sanitize_filename(self, title: str, url: str) -> str:
        """Create a safe filename from title or URL"""
        if title:
            name = title
        else:
            # Use last part of URL path
            name = url.rstrip('/').split('/')[-1] or 'page'
        
        # Remove/replace unsafe characters
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = re.sub(r'\s+', '_', name)
        name = name[:50]  # Limit length
        
        return f"{name}.md"
    
    async def crawl_page(self, url: str, title: str = "") -> PageResult:
        """Crawl a single page"""
        try:
            # Try static parser first
            result = self.static_parser.parse(url)
            
            if not result.success:
                # Fallback to dynamic parser
                result = self.dynamic_parser.parse(url)
            
            if result.success:
                page_title = result.title or title or url
                filename = self._sanitize_filename(page_title, url)
                
                return PageResult(
                    url=url,
                    title=page_title,
                    filename=filename,
                    markdown=result.markdown or "",
                    success=True
                )
            else:
                return PageResult(
                    url=url,
                    title=title or url,
                    filename=self._sanitize_filename(title, url),
                    markdown="",
                    success=False,
                    error=result.error
                )
        except Exception as e:
            return PageResult(
                url=url,
                title=title or url,
                filename=self._sanitize_filename(title, url),
                markdown="",
                success=False,
                error=str(e)
            )
    
    async def crawl_batch(
        self, 
        pages: List[Dict[str, str]], 
        max_pages: int = 50
    ) -> AsyncGenerator[tuple, None]:
        """
        Crawl multiple pages with progress updates.
        Yields (progress, result) tuples.
        """
        pages = pages[:max_pages]
        total = len(pages)
        results = []
        
        for i, page in enumerate(pages):
            url = page.get('url', '')
            title = page.get('title', '')
            
            # Yield progress before crawling
            progress = BatchProgress(
                current=i + 1,
                total=total,
                current_url=url,
                current_title=title,
                status="crawling"
            )
            yield (progress, None)
            
            # Crawl the page
            result = await self.crawl_page(url, title)
            results.append(result)
            
            # Small delay to avoid overwhelming servers
            await asyncio.sleep(0.5)
        
        # Final progress
        final_progress = BatchProgress(
            current=total,
            total=total,
            current_url="",
            current_title="",
            status="done"
        )
        yield (final_progress, results)
    
    def crawl_batch_sync(
        self, 
        pages: List[Dict[str, str]], 
        max_pages: int = 50
    ) -> List[PageResult]:
        """Synchronous batch crawl"""
        pages = pages[:max_pages]
        results = []
        
        for page in pages:
            url = page.get('url', '')
            title = page.get('title', '')
            
            # Crawl synchronously
            try:
                result = self.static_parser.parse(url)
                if not result.success:
                    result = self.dynamic_parser.parse(url)
                
                if result.success:
                    page_title = result.title or title or url
                    filename = self._sanitize_filename(page_title, url)
                    results.append(PageResult(
                        url=url,
                        title=page_title,
                        filename=filename,
                        markdown=result.markdown or "",
                        success=True
                    ))
                else:
                    results.append(PageResult(
                        url=url,
                        title=title or url,
                        filename=self._sanitize_filename(title, url),
                        markdown="",
                        success=False,
                        error=result.error
                    ))
            except Exception as e:
                results.append(PageResult(
                    url=url,
                    title=title or url,
                    filename=self._sanitize_filename(title, url),
                    markdown="",
                    success=False,
                    error=str(e)
                ))
        
        return results
    
    def create_zip(self, results: List[PageResult]) -> bytes:
        """Create a ZIP file containing all markdown files"""
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            seen_filenames = set()
            
            for result in results:
                if not result.success or not result.markdown:
                    continue
                
                # Ensure unique filename
                filename = result.filename
                base_name = filename.rsplit('.', 1)[0]
                counter = 1
                while filename in seen_filenames:
                    filename = f"{base_name}_{counter}.md"
                    counter += 1
                seen_filenames.add(filename)
                
                # Add to zip
                zf.writestr(filename, result.markdown.encode('utf-8'))
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def merge_markdown(self, results: List[PageResult]) -> str:
        """Merge all pages into a single markdown file"""
        sections = []
        
        sections.append("# 完整文档\n")
        sections.append(f"共 {len([r for r in results if r.success])} 个页面\n")
        sections.append("---\n\n")
        
        for i, result in enumerate(results, 1):
            if not result.success or not result.markdown:
                continue
            
            sections.append(f"## 第{i}章: {result.title}\n")
            sections.append(f"*来源: {result.url}*\n\n")
            
            # Remove the title from content if it starts with #
            content = result.markdown
            if content.startswith('# '):
                # Skip the first line (title)
                lines = content.split('\n', 1)
                if len(lines) > 1:
                    content = lines[1].strip()
            
            sections.append(content)
            sections.append("\n\n---\n\n")
        
        return '\n'.join(sections)
