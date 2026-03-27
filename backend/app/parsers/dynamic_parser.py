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
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = context.new_page()

                # Navigate with shorter timeout (15 seconds)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    # Wait a bit for dynamic content
                    page.wait_for_timeout(2000)
                except Exception as nav_error:
                    print(f"    [Dynamic] Navigation timeout: {nav_error}")
                    browser.close()
                    return ParseResult(success=False, error=f"Navigation timeout")

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
        """Heuristic detection of article body"""
        selectors = [
            ('article', {}),
            ('main', {}),
            ('div', {'class_': 'content'}),
            ('div', {'class_': 'article'}),
            ('div', {'class_': 'post'}),
            ('div', {'id': 'content'}),
            ('div', {'id': 'main'}),
            ('div', {'role': 'main'}),
        ]

        for tag, attrs in selectors:
            content = soup.find(tag, **attrs)
            if content and len(content.get_text(strip=True)) > 100:
                return content

        return None
