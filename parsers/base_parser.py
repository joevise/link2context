import re
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
        # Use word boundary matching for classes/ids
        noise_classes = [
            r'ad', r'ads?', r'advertisement', r'banner', r'sidebar',
            r'comment', r'comments', r'share', r'social', r'related',
            r'recommend', r'footer', r'header', r'navigation'
        ]
        noise_ids = [
            r'ad', r'ads?', r'sidebar', r'comment', r'comments',
            r'footer', r'header', r'navigation'
        ]

        # Remove noise tags (except iframe for video detection)
        for tag in noise_tags:
            if tag != 'iframe':  # Keep iframes for video detection
                for element in soup.find_all(tag):
                    element.decompose()

        # Remove elements with noise classes (word boundary match)
        for element in soup.find_all(class_=True):
            classes = element.get('class', [])
            if not classes:
                continue
            if isinstance(classes, str):
                classes = classes.split()
            classes_str = ' '.join(classes)
            for pattern in noise_classes:
                if re.search(pattern, classes_str, re.I):
                    element.decompose()
                    break

        # Remove elements with noise ids (word boundary match)
        for element in soup.find_all(id_=True):
            id_val = element.get('id', '')
            if not id_val:
                continue
            for pattern in noise_ids:
                if re.search(pattern, id_val, re.I):
                    element.decompose()
                    break

        return soup
