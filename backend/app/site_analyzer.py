import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Optional
from dataclasses import dataclass
from fake_useragent import UserAgent
import requests
import json


@dataclass
class AnalyzerConfig:
    provider: str  # openai, claude, custom
    base_url: str
    api_key: str
    model: str
    prompt: str


@dataclass
class SiteStructure:
    success: bool
    base_url: str
    pages: List[dict] = None  # [{url, title}, ...]
    error: Optional[str] = None


class SiteAnalyzer:
    """Analyze website structure to discover documentation pages"""
    
    DEFAULT_PROMPT = """分析这个网页的HTML内容，找出所有的文档/帮助页面链接。

要求：
1. 重点关注导航栏、侧边栏、目录中的链接
2. 只提取文档/教程/指南类的页面链接
3. 忽略外部链接、登录/注册链接、社交媒体链接
4. 返回JSON格式的链接列表

返回格式（只返回JSON，不要其他内容）：
{
  "pages": [
    {"url": "/docs/introduction", "title": "介绍"},
    {"url": "/docs/getting-started", "title": "快速开始"},
    ...
  ]
}

如果没有找到文档链接，返回：
{"pages": []}
"""

    def __init__(self, config: AnalyzerConfig):
        self.config = config
        self.prompt = config.prompt or self.DEFAULT_PROMPT
    
    def _fetch_page_static(self, url: str) -> Optional[str]:
        """Fetch page HTML content using static request"""
        try:
            ua = UserAgent()
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Static fetch failed for {url}: {e}")
            return None
    
    def _fetch_page_dynamic(self, url: str) -> Optional[str]:
        """Fetch page HTML content using Playwright for dynamic sites"""
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wait for SPA frameworks to render
                try:
                    page.wait_for_selector('nav, aside, .sidebar, [class*="sidebar"], [class*="menu"]', timeout=5000)
                except:
                    pass
                page.wait_for_timeout(3000)
                
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"Dynamic fetch failed for {url}: {e}")
            return None
    
    def _extract_links_basic(self, html: str, base_url: str) -> List[dict]:
        """Basic link extraction from navigation elements"""
        soup = BeautifulSoup(html, 'lxml')
        links = []
        seen_urls = set()
        
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        
        # Look for common navigation/sidebar elements - expanded selectors
        nav_selectors = [
            'nav', 'aside', '.sidebar', '.nav', '.menu', '.toc',
            '[class*="sidebar"]', '[class*="navigation"]', '[class*="menu"]',
            '[class*="docs"]', '[class*="toc"]', '[id*="sidebar"]',
            '[id*="nav"]', '[id*="menu"]', '[class*="list"]',
            '[class*="tree"]', '[class*="index"]', '[class*="contents"]',
            '[class*="drawer"]', '[class*="panel"]', 'ul', 'ol'
        ]
        
        nav_elements = []
        for selector in nav_selectors:
            try:
                elements = soup.select(selector)
                nav_elements.extend(elements)
            except:
                continue
        
        # If no nav elements found, use the whole page
        if not nav_elements:
            nav_elements = [soup]
        
        print(f"Found {len(nav_elements)} navigation elements")
        
        for nav in nav_elements:
            for a in nav.find_all('a', href=True):
                href = a.get('href', '')
                title = a.get_text(strip=True)
                
                if not href or not title:
                    continue
                
                # Skip common non-doc links
                skip_patterns = [
                    r'^#$', r'^javascript:', r'^mailto:', r'^tel:',
                    r'login', r'signin', r'signup', r'register',
                    r'twitter\.com', r'facebook\.com', r'linkedin\.com',
                    r'\.(png|jpg|gif|pdf|zip|exe|dmg)$'
                ]
                if any(re.search(p, href, re.I) for p in skip_patterns):
                    continue
                
                # Handle anchor links - keep if they're different pages
                if href.startswith('#'):
                    continue
                
                # Convert to absolute URL
                full_url = urljoin(base_url, href)
                parsed_url = urlparse(full_url)
                
                # Only include same-domain links
                if parsed_url.netloc != base_domain:
                    continue
                
                # Normalize URL (remove trailing slash and fragment)
                normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                if normalized_url.endswith('/'):
                    normalized_url = normalized_url[:-1]
                
                base_normalized = base_url.rstrip('/')
                
                if normalized_url not in seen_urls and normalized_url != base_normalized:
                    seen_urls.add(normalized_url)
                    links.append({
                        "url": normalized_url,
                        "title": title[:100]  # Limit title length
                    })
        
        print(f"Basic extraction found {len(links)} unique links")
        return links
    
    async def analyze_with_ai(self, html: str, base_url: str) -> List[dict]:
        """Use AI to analyze page structure and find documentation links"""
        # First get basic links
        basic_links = self._extract_links_basic(html, base_url)
        
        if not self.config.api_key:
            print("No API key configured, using basic extraction only")
            return basic_links
        
        try:
            print(f"Calling AI ({self.config.provider}/{self.config.model}) for analysis...")
            
            # Prepare HTML summary (limit size for AI)
            soup = BeautifulSoup(html, 'lxml')
            
            # Remove scripts, styles
            for tag in soup.find_all(['script', 'style', 'noscript', 'svg', 'path']):
                tag.decompose()
            
            # Get text content with structure hints - focus on nav elements
            nav_html = ""
            for selector in ['nav', 'aside', '[class*="sidebar"]', '[class*="menu"]', '[class*="nav"]']:
                try:
                    for el in soup.select(selector):
                        nav_html += str(el)
                except:
                    pass
            
            # If we found nav elements, use them; otherwise use limited page content
            if len(nav_html) > 500:
                html_summary = nav_html[:20000]
            else:
                html_summary = str(soup)[:20000]
            
            prompt = f"""{self.prompt}

网页URL: {base_url}

HTML内容:
{html_summary}
"""
            
            if self.config.provider == 'claude':
                result = await self._call_claude(prompt)
            else:
                result = await self._call_openai(prompt)
            
            print(f"AI response received, parsing...")
            
            # Parse AI response
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                data = json.loads(json_match.group())
                ai_pages = data.get('pages', [])
                
                print(f"AI found {len(ai_pages)} pages")
                
                # Convert relative URLs to absolute
                for page in ai_pages:
                    if not page['url'].startswith('http'):
                        page['url'] = urljoin(base_url, page['url'])
                
                # Merge AI results with basic links (prefer AI results)
                if len(ai_pages) > 0:
                    return ai_pages
            
            print("AI parsing failed or returned empty, using basic extraction")
            return basic_links
            
        except Exception as e:
            print(f"AI analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return basic_links
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.1
        }
        
        print(f"Calling OpenAI API: {url}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
    
    async def _call_claude(self, prompt: str) -> str:
        """Call Claude API"""
        url = f"{self.config.base_url.rstrip('/')}/messages"
        
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        print(f"Calling Claude API: {url}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data['content'][0]['text']
    
    async def analyze(self, url: str) -> SiteStructure:
        """Analyze a website and return its documentation structure.
        Uses direct link extraction without AI - simpler and faster.
        """
        print(f"\n=== Analyzing site: {url} ===")
        
        # First try static fetch
        html = self._fetch_page_static(url)
        
        # Check if page seems to be dynamic (minimal content)
        if html:
            soup = BeautifulSoup(html, 'lxml')
            text_content = soup.get_text(strip=True)
            link_count = len(soup.find_all('a', href=True))
            print(f"Static fetch: {len(html)} chars, {link_count} links, {len(text_content)} text chars")
            
            # If very little content, try dynamic fetch
            if len(text_content) < 500 or link_count < 5:
                print("Page appears to be dynamically rendered, trying Playwright...")
                dynamic_html = self._fetch_page_dynamic(url)
                if dynamic_html:
                    dyn_soup = BeautifulSoup(dynamic_html, 'lxml')
                    dyn_link_count = len(dyn_soup.find_all('a', href=True))
                    print(f"Dynamic fetch: {len(dynamic_html)} chars, {dyn_link_count} links")
                    if dyn_link_count > link_count:
                        html = dynamic_html
        else:
            # Static failed, try dynamic
            print("Static fetch failed, trying Playwright...")
            html = self._fetch_page_dynamic(url)
        
        if not html:
            return SiteStructure(
                success=False,
                base_url=url,
                error="Failed to fetch page (both static and dynamic methods failed)"
            )
        
        # Direct link extraction - no AI needed, user can select which ones to crawl
        pages = self._extract_links_basic(html, url)
        print(f"Direct extraction found {len(pages)} links")
        
        # Add the original URL as first page if not already included
        original_normalized = url.rstrip('/')
        if not any(p['url'].rstrip('/') == original_normalized for p in pages):
            pages.insert(0, {"url": url, "title": "首页"})
        
        print(f"=== Analysis complete: {len(pages)} pages found ===\n")
        
        return SiteStructure(
            success=True,
            base_url=url,
            pages=pages
        )
