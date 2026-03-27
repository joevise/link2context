import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from .base_parser import BaseParser, ParseResult, MediaInfo
from ..media_handler import MediaHandler


class DynamicParser(BaseParser):
    """Dynamic fallback using headless browser (Playwright)"""

    def can_handle(self, url: str) -> bool:
        # Can handle any URL as last resort
        return True

    def parse(self, url: str) -> ParseResult:
        try:
            from playwright.sync_api import sync_playwright
            
            print(f"    [Dynamic] Starting Playwright for: {url[:60]}...")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = browser.new_page()
                
                # For SPA/Next.js sites: use domcontentloaded + wait for JS rendering
                # 'load' hangs on sites with streaming/SSE connections
                try:
                    page.goto(url, timeout=30000, wait_until='domcontentloaded')
                except Exception:
                    # Fallback: some sites need even longer
                    page.goto(url, timeout=60000, wait_until='commit')
                
                # Wait for JS frameworks to render content
                # Try to wait for common SPA content selectors
                try:
                    page.wait_for_selector('article, main, [role="main"], .content, #content, .markdown, .docs-content', timeout=8000)
                except Exception:
                    pass  # Selector not found, just wait fixed time
                
                page.wait_for_timeout(3000)  # Extra buffer for lazy-loaded content

                # Get page title
                title = page.title() or "Untitled"

                # Get page content
                html_content = page.content()
                print(f"    [Dynamic] Got content: {len(html_content)} chars")

                browser.close()

            soup = BeautifulSoup(html_content, 'lxml')
            
            # Initialize media handler
            media_handler = MediaHandler(base_url=url)

            # Detect videos before cleaning
            videos = media_handler.detect_videos(html_content, soup)

            # Clean the DOM
            soup = self.clean_html(soup)

            # Try to find main content
            content = self._extract_main_content(soup)

            if not content:
                content = soup.find('body')

            if not content:
                return ParseResult(success=False, error="Could not extract content")

            # Download and cache images
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            content, image_map = media_handler.process_images_in_soup(content, headers)

            # Convert to markdown
            markdown_content = md(str(content), heading_style="ATX")

            # Clean up
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = markdown_content.strip()

            if len(markdown_content) < 50:
                return ParseResult(success=False, error="Content extraction failed")

            full_markdown = f"# {title}\n\n{markdown_content}"
            
            # Create version with local images
            markdown_with_local = media_handler.get_markdown_with_local_images(full_markdown, image_map)
            
            # Add videos
            markdown_with_local = media_handler.add_videos_to_markdown(markdown_with_local, videos)
            full_markdown = media_handler.add_videos_to_markdown(full_markdown, videos)

            # Prepare media info
            media_info = MediaInfo(
                images=image_map,
                videos=[{
                    'url': v.original_url,
                    'thumbnail': v.thumbnail_url,
                    'local_thumbnail': v.local_path
                } for v in videos]
            )

            return ParseResult(
                success=True, 
                title=title, 
                markdown=full_markdown,
                markdown_with_local_images=markdown_with_local,
                media=media_info
            )

        except Exception as e:
            return ParseResult(success=False, error=f"Dynamic parse error: {str(e)}")

    def _extract_main_content(self, soup):
        """Heuristic detection of article body — SPA/docs site aware"""
        selectors = [
            # Documentation frameworks (VitePress, Docusaurus, GitBook, Nextra, etc.)
            ('div', {'class_': re.compile(r'vp-doc|docs-content|markdown-body|prose|nextra')}),
            ('div', {'class_': re.compile(r'theme-default-content|page-content')}),
            # Standard semantic HTML
            ('article', {}),
            ('main', {}),
            ('[role=main]', {}),
            # Common class patterns
            ('div', {'class_': re.compile(r'^content$|^article$|^post$|^entry')}),
            ('div', {'id': re.compile(r'^content$|^main$|^article$')}),
            ('div', {'role': 'main'}),
        ]

        for selector_or_tag, attrs in selectors:
            # Handle CSS-style selectors
            if selector_or_tag.startswith('['):
                content = soup.select_one(selector_or_tag)
            else:
                content = soup.find(selector_or_tag, **attrs) if attrs else soup.find(selector_or_tag)
            if content and len(content.get_text(strip=True)) > 100:
                return content

        # Last resort: find the div with the most text content
        best = None
        best_len = 0
        for div in soup.find_all('div'):
            text = div.get_text(strip=True)
            if len(text) > best_len and len(text) > 200:
                # Avoid full-page wrappers (check depth)
                children_divs = div.find_all('div', recursive=False)
                if len(children_divs) < 20:  # Not a top-level wrapper
                    best = div
                    best_len = len(text)
        
        return best
