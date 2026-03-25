import os
import re
import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Cache directory
CACHE_DIR = Path(__file__).parent / "cache" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MediaItem:
    original_url: str
    local_path: Optional[str] = None
    media_type: str = "image"  # image or video
    thumbnail_url: Optional[str] = None


class MediaHandler:
    """Handle downloading and caching of images and video detection"""
    
    VIDEO_PATTERNS = [
        r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+)',
        r'(https?://(?:www\.)?youtu\.be/[\w-]+)',
        r'(https?://(?:www\.)?bilibili\.com/video/[\w]+)',
        r'(https?://(?:www\.)?vimeo\.com/\d+)',
        r'(https?://v\.qq\.com/[\w/]+)',
        r'(https?://(?:www\.)?douyin\.com/video/\d+)',
        r'(https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+)',
    ]
    
    VIDEO_EXTENSIONS = ['.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv']
    
    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self.downloaded_images: Dict[str, str] = {}
        self.detected_videos: List[MediaItem] = []
    
    def get_image_hash(self, url: str) -> str:
        """Generate a unique hash for image URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def download_image(self, url: str, headers: dict = None, timeout: float = 8.0) -> Optional[str]:
        """Download image and save to cache, return local filename.
        Uses short timeout to avoid blocking on unreachable resources.
        """
        if not url or url.startswith('data:'):
            return None
            
        # Make absolute URL
        if not url.startswith(('http://', 'https://')):
            url = urljoin(self.base_url, url)
        
        # Check if already downloaded
        if url in self.downloaded_images:
            return self.downloaded_images[url]
        
        try:
            default_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": self.base_url or url,
            }
            if headers:
                default_headers.update(headers)
            
            response = requests.get(url, headers=default_headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            ext = self._get_extension(url, content_type)
            
            # Generate filename
            img_hash = self.get_image_hash(url)
            filename = f"{img_hash}{ext}"
            filepath = CACHE_DIR / filename
            
            # Save image
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            self.downloaded_images[url] = filename
            return filename
            
        except Exception as e:
            print(f"Warning: Failed to download image {url}: {e}")
            return None
    
    def _get_extension(self, url: str, content_type: str) -> str:
        """Get file extension from URL or content-type"""
        # Try from URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']:
            if path.endswith(ext):
                return ext
        
        # Try from content-type
        type_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/svg+xml': '.svg',
            'image/bmp': '.bmp',
        }
        for mime, ext in type_map.items():
            if mime in content_type:
                return ext
        
        return '.jpg'  # Default
    
    def detect_videos(self, html: str, soup=None) -> List[MediaItem]:
        """Detect video links in HTML content"""
        videos = []
        seen_urls = set()
        
        # Pattern matching for video URLs
        for pattern in self.VIDEO_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for url in matches:
                if url not in seen_urls:
                    seen_urls.add(url)
                    thumbnail = self._get_video_thumbnail(url)
                    videos.append(MediaItem(
                        original_url=url,
                        media_type="video",
                        thumbnail_url=thumbnail
                    ))
        
        # Check for video tags
        if soup:
            for video in soup.find_all('video'):
                src = video.get('src')
                if src and src not in seen_urls:
                    seen_urls.add(src)
                    poster = video.get('poster')
                    videos.append(MediaItem(
                        original_url=src if src.startswith('http') else urljoin(self.base_url, src),
                        media_type="video",
                        thumbnail_url=poster
                    ))
                
                # Check source tags
                for source in video.find_all('source'):
                    src = source.get('src')
                    if src and src not in seen_urls:
                        seen_urls.add(src)
                        videos.append(MediaItem(
                            original_url=src if src.startswith('http') else urljoin(self.base_url, src),
                            media_type="video",
                            thumbnail_url=video.get('poster')
                        ))
            
            # Check for iframe embeds (YouTube, etc.)
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if any(domain in src for domain in ['youtube', 'youtu.be', 'bilibili', 'vimeo', 'qq.com']):
                    if src not in seen_urls:
                        seen_urls.add(src)
                        thumbnail = self._get_video_thumbnail(src)
                        videos.append(MediaItem(
                            original_url=src,
                            media_type="video",
                            thumbnail_url=thumbnail
                        ))
        
        self.detected_videos = videos
        return videos
    
    def _get_video_thumbnail(self, url: str) -> Optional[str]:
        """Try to get video thumbnail URL"""
        # YouTube
        youtube_match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]+)', url)
        if youtube_match:
            video_id = youtube_match.group(1)
            return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        # Bilibili - would need API call, return None for now
        # Other platforms similar
        
        return None
    
    def process_images_in_soup(self, soup, headers: dict = None) -> Tuple[any, Dict[str, str]]:
        """Process all images in BeautifulSoup object, download and replace URLs.
        Uses thread pool to download images concurrently with short timeout.
        """
        image_map = {}  # original_url -> local_filename
        
        # Collect all images first
        images_to_download = []
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('data-original') or img.get('src')
            if not src:
                continue
            images_to_download.append((img, src))
        
        # Download concurrently with thread pool
        def download_one(img, src):
            local_filename = self.download_image(src, headers)
            return img, src, local_filename
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(download_one, img, src): (img, src) 
                      for img, src in images_to_download}
            for future in as_completed(futures, timeout=30):
                try:
                    img, src, local_filename = future.result()
                    if local_filename:
                        image_map[src] = local_filename
                        img['src'] = f"/api/images/{local_filename}"
                        img['data-original-src'] = src
                except Exception as e:
                    img, src, _ = futures[future]
                    print(f"Warning: Image download failed for {src}: {e}")
        
        return soup, image_map
    
    def get_markdown_with_local_images(self, markdown: str, image_map: Dict[str, str]) -> str:
        """Replace image URLs in markdown with local paths"""
        result = markdown
        for original_url, local_filename in image_map.items():
            # Replace markdown image syntax
            result = result.replace(f"]({original_url})", f"](/api/images/{local_filename})")
            result = result.replace(f'src="{original_url}"', f'src="/api/images/{local_filename}"')
        return result
    
    def add_videos_to_markdown(self, markdown: str, videos: List[MediaItem]) -> str:
        """Add video sections to markdown"""
        if not videos:
            return markdown
        
        video_section = "\n\n---\n\n## 📹 视频内容\n\n"
        for i, video in enumerate(videos, 1):
            if video.thumbnail_url:
                # Download thumbnail
                thumb_filename = self.download_image(video.thumbnail_url)
                if thumb_filename:
                    video_section += f"![视频{i}封面](/api/images/{thumb_filename})\n\n"
                else:
                    video_section += f"![视频{i}封面]({video.thumbnail_url})\n\n"
            
            video_section += f"🎬 **视频链接{i}**: [{video.original_url}]({video.original_url})\n\n"
        
        return markdown + video_section
