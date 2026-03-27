from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class MediaInfo:
    images: Dict[str, str] = field(default_factory=dict)  # original_url -> local_filename
    videos: List[dict] = field(default_factory=list)  # list of video info


@dataclass
class ParseResult:
    success: bool
    title: Optional[str] = None
    markdown: Optional[str] = None
    markdown_with_local_images: Optional[str] = None
    error: Optional[str] = None
    media: Optional[MediaInfo] = None


class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this parser can handle the given URL"""
        pass

    @abstractmethod
    def parse(self, url: str) -> ParseResult:
        """Parse the URL and return markdown content"""
        pass

    def clean_html(self, soup):
        """Remove common noise elements from HTML"""
        noise_tags = [
            'script', 'style', 'nav', 'footer', 'header', 'aside',
            'iframe', 'noscript', 'form', 'button', 'input',
            'select', 'textarea', 'meta', 'link'
        ]
        noise_classes = [
            'ad', 'ads', 'advertisement', 'banner', 'sidebar',
            'comment', 'comments', 'share', 'social', 'related',
            'recommend', 'footer', 'header', 'nav', 'navigation'
        ]
        noise_ids = [
            'ad', 'ads', 'sidebar', 'comment', 'comments',
            'footer', 'header', 'nav', 'navigation'
        ]

        # Remove noise tags (except iframe for video detection)
        for tag in noise_tags:
            if tag != 'iframe':  # Keep iframes for video detection
                for element in soup.find_all(tag):
                    element.decompose()

        # Remove elements with noise classes
        for class_name in noise_classes:
            for element in soup.find_all(class_=lambda x: x and class_name in str(x).lower()):
                element.decompose()

        # Remove elements with noise ids
        for id_name in noise_ids:
            for element in soup.find_all(id=lambda x: x and id_name in str(x).lower()):
                element.decompose()

        return soup
