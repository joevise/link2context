import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from fake_useragent import UserAgent

from .base_parser import BaseParser, ParseResult, MediaInfo
from ..media_handler import MediaHandler


class WeChatParser(BaseParser):
    """Special handler for WeChat Public Platform articles"""

    def can_handle(self, url: str) -> bool:
        return "mp.weixin.qq.com" in url

    def parse(self, url: str) -> ParseResult:
        try:
            ua = UserAgent()
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'lxml')
            
            # Initialize media handler
            media_handler = MediaHandler(base_url=url)

            # Get title
            title_elem = soup.find('h1', class_='rich_media_title') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "WeChat Article"

            # Find content container
            content = soup.find(id='js_content')
            if not content:
                content = soup.find(class_='rich_media_content')

            if not content:
                return ParseResult(success=False, error="Could not find WeChat content container")

            # Fix lazy loading images - Critical!
            for img in content.find_all('img'):
                data_src = img.get('data-src')
                if data_src:
                    img['src'] = data_src

            # Detect videos before cleaning
            videos = media_handler.detect_videos(str(content), content)

            # Remove WeChat clutter
            for qr in content.find_all(class_=lambda x: x and 'qr' in str(x).lower()):
                qr.decompose()

            # Remove iframes after video detection
            for iframe in content.find_all('iframe'):
                iframe.decompose()

            # Clean DOM
            content = self.clean_html(content)
            
            # Download and cache images
            content, image_map = media_handler.process_images_in_soup(content, headers)

            # Convert to markdown
            markdown_content = md(str(content), heading_style="ATX", strip=['a'])

            # Clean up excessive newlines
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = markdown_content.strip()

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
