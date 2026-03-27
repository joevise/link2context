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
    
    def crawl_single_page(self, url: str, title: str = "") -> PageResult:
        """Crawl a single page - used by SSE streaming endpoint"""
        print(f"  Crawling: {title[:30]}... ({url[:50]})")
        
        try:
            # Try static parser first
            result = self.static_parser.parse(url)
            
            # Check if page requires login
            if result.success and self._requires_login(result.markdown):
                print(f"  ⚠ Detected login required, skipping...")
                return PageResult(
                    url=url,
                    title=title or url,
                    filename=self._sanitize_filename(title, url),
                    markdown="",
                    success=False,
                    error="Requires login"
                )
            
            # If static failed, try dynamic parser
            if not result.success:
                error_msg = result.error or ""
                
                # Skip dynamic for pages that are clearly inaccessible
                if "too short" in error_msg.lower() or "blocked" in error_msg.lower():
                    print(f"  ⚠ Static got no content, skipping...")
                    return PageResult(
                        url=url,
                        title=title or url,
                        filename=self._sanitize_filename(title, url),
                        markdown="",
                        success=False,
                        error="No accessible content"
                    )
                
                # Always try dynamic for any page (SPA/Next.js sites need it)
                print(f"  Static failed, trying dynamic...")
                result = self.dynamic_parser.parse(url)
                
                if result.success and self._requires_login(result.markdown):
                    return PageResult(
                        url=url,
                        title=title or url,
                        filename=self._sanitize_filename(title, url),
                        markdown="",
                        success=False,
                        error="Requires login"
                    )
            
            if result.success:
                page_title = result.title or title or url
                filename = self._sanitize_filename(page_title, url)
                print(f"  ✓ Success: {len(result.markdown or '')} chars")
                return PageResult(
                    url=url,
                    title=page_title,
                    filename=filename,
                    markdown=result.markdown or "",
                    success=True
                )
            else:
                print(f"  ✗ Failed: {result.error}")
                return PageResult(
                    url=url,
                    title=title or url,
                    filename=self._sanitize_filename(title, url),
                    markdown="",
                    success=False,
                    error=result.error
                )
                
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            return PageResult(
                url=url,
                title=title or url,
                filename=self._sanitize_filename(title, url),
                markdown="",
                success=False,
                error=str(e)
            )
    
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
    
    def _requires_login(self, markdown: str) -> bool:
        """
        Detect if a page requires login by analyzing its content.
        This is a universal method that works for any website.
        
        Strategy:
        1. If content is very short AND contains login keywords -> requires login
        2. If content mentions access denied / unauthorized -> requires login
        3. Otherwise -> accessible
        """
        if not markdown:
            return True
        
        content_lower = markdown.lower()
        content_length = len(markdown)
        
        # Login-related keywords (multi-language)
        login_keywords = [
            # Chinese
            '登录', '登入', '请先登录', '需要登录', '请登录后', '登录后查看',
            '请先登入', '账号登录', '用户登录', '会员登录',
            # English
            'login', 'log in', 'sign in', 'signin', 'please log in',
            'authentication required', 'must be logged in', 'login required',
            'please sign in', 'sign in to continue'
        ]
        
        # Access denied keywords
        access_denied_keywords = [
            # Chinese
            '权限不足', '无权访问', '访问被拒绝', '需要授权', '没有权限',
            '禁止访问', '未授权', '请先授权',
            # English
            'forbidden', 'access denied', 'unauthorized', 'not authorized',
            'permission denied', 'access restricted'
        ]
        
        # Check 1: Very little content with login keywords
        # If page has < 200 chars and mentions login, it's likely a login gate
        if content_length < 200:
            if any(kw in content_lower for kw in login_keywords):
                return True
            if any(kw in content_lower for kw in access_denied_keywords):
                return True
        
        # Check 2: Short content with heavy login emphasis
        # If page has < 500 chars and login keywords appear multiple times
        if content_length < 500:
            login_count = sum(1 for kw in login_keywords if kw in content_lower)
            if login_count >= 2:
                return True
        
        # Check 3: Page title/heading mentions login (anywhere in content)
        # Look for patterns like "# 登录" or "## Sign In"
        if '# 登录' in markdown or '# login' in content_lower or '# sign in' in content_lower:
            if content_length < 1000:
                return True
        
        return False
    
    def crawl_batch_sync(
        self, 
        pages: List[Dict[str, str]], 
        max_pages: int = 50
    ) -> List[PageResult]:
        """Synchronous batch crawl with smart login detection"""
        pages = pages[:max_pages]
        results = []
        total = len(pages)
        
        print(f"\n=== Starting batch crawl: {total} pages ===")
        
        for i, page in enumerate(pages, 1):
            url = page.get('url', '')
            title = page.get('title', '')
            
            print(f"[{i}/{total}] Crawling: {title[:30]}... ({url[:50]})")
            
            try:
                # Try static parser first
                result = self.static_parser.parse(url)
                
                # Check if page requires login
                if result.success and self._requires_login(result.markdown):
                    print(f"  ⚠ Detected login required, skipping...")
                    results.append(PageResult(
                        url=url,
                        title=title or url,
                        filename=self._sanitize_filename(title, url),
                        markdown="",
                        success=False,
                        error="Requires login"
                    ))
                    continue
                
                # If static failed, try dynamic parser
                if not result.success:
                    error_msg = result.error or ""
                    
                    # Skip dynamic for pages that are clearly inaccessible
                    if "too short" in error_msg.lower() or "blocked" in error_msg.lower():
                        print(f"  ⚠ Static got no content, likely requires login, skipping dynamic...")
                        results.append(PageResult(
                            url=url,
                            title=title or url,
                            filename=self._sanitize_filename(title, url),
                            markdown="",
                            success=False,
                            error="No accessible content"
                        ))
                        continue
                    
                    # Always try dynamic for any page (SPA/Next.js sites need it)
                    print(f"  Static failed, trying dynamic...")
                    result = self.dynamic_parser.parse(url)
                    
                    # Check login requirement again
                    if result.success and self._requires_login(result.markdown):
                        print(f"  ⚠ Detected login required, skipping...")
                        results.append(PageResult(
                            url=url,
                            title=title or url,
                            filename=self._sanitize_filename(title, url),
                            markdown="",
                            success=False,
                            error="Requires login"
                        ))
                        continue
                
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
                    print(f"  ✓ Success: {len(result.markdown or '')} chars")
                else:
                    results.append(PageResult(
                        url=url,
                        title=title or url,
                        filename=self._sanitize_filename(title, url),
                        markdown="",
                        success=False,
                        error=result.error
                    ))
                    print(f"  ✗ Failed: {result.error}")
                    
            except Exception as e:
                results.append(PageResult(
                    url=url,
                    title=title or url,
                    filename=self._sanitize_filename(title, url),
                    markdown="",
                    success=False,
                    error=str(e)
                ))
                print(f"  ✗ Exception: {e}")
        
        success_count = len([r for r in results if r.success])
        print(f"=== Batch crawl complete: {success_count}/{total} succeeded ===\n")
        
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
