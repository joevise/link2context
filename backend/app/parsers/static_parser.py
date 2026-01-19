import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from fake_useragent import UserAgent

from .base_parser import BaseParser, ParseResult, MediaInfo
from ..media_handler import MediaHandler


class StaticParser(BaseParser):
    """General static page parser - speed & cost optimized"""

    def can_handle(self, url: str) -> bool:
        # Can handle any URL as fallback
        return True

    def parse(self, url: str) -> ParseResult:
        try:
            ua = UserAgent()
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            }

            response = requests.get(url, headers=headers, timeout=30)

            # Check for blocking
            if response.status_code in [403, 401]:
                return ParseResult(success=False, error="Access blocked - need dynamic parser")

            response.raise_for_status()

            # Try to detect encoding
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'lxml')
            
            # Initialize media handler
            media_handler = MediaHandler(base_url=url)

            # Get title
            title_elem = soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"

            # Detect videos before cleaning
            videos = media_handler.detect_videos(response.text, soup)

            # Clean the DOM
            soup = self.clean_html(soup)

            # Try to find main content using heuristics
            content = self._extract_main_content(soup)

            if not content:
                return ParseResult(success=False, error="Could not extract main content")

            # Download and cache images
            content, image_map = media_handler.process_images_in_soup(content, headers)

            # Convert to markdown
            markdown_content = md(str(content), heading_style="ATX")

            # Clean up
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = re.sub(r'^\s+', '', markdown_content, flags=re.MULTILINE)
            markdown_content = markdown_content.strip()

            if len(markdown_content) < 50:
                return ParseResult(success=False, error="Content too short - may need dynamic parser")

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

        except requests.RequestException as e:
            return ParseResult(success=False, error=f"Request failed: {str(e)}")
        except Exception as e:
            return ParseResult(success=False, error=f"Parse error: {str(e)}")

    def _extract_main_content(self, soup):
        """Heuristic detection of article body"""
        # Priority list of content containers
        selectors = [
            ('article', {}),
            ('main', {}),
            ('div', {'class_': 'content'}),
            ('div', {'class_': 'article'}),
            ('div', {'class_': 'post'}),
            ('div', {'class_': 'entry'}),
            ('div', {'class_': 'post-content'}),
            ('div', {'class_': 'article-content'}),
            ('div', {'class_': 'entry-content'}),
            ('div', {'id': 'content'}),
            ('div', {'id': 'article'}),
            ('div', {'id': 'main'}),
            ('div', {'role': 'main'}),
        ]

        for tag, attrs in selectors:
            content = soup.find(tag, **attrs)
            if content and len(content.get_text(strip=True)) > 100:
                return content

        # Fallback: find the div with most text
        body = soup.find('body')
        if body:
            divs = body.find_all('div', recursive=True)
            if divs:
                best_div = max(divs, key=lambda d: len(d.get_text(strip=True)))
                if len(best_div.get_text(strip=True)) > 100:
                    return best_div

        return body
