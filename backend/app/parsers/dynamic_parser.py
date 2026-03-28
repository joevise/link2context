import re
import json
import subprocess
import sys
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from .base_parser import BaseParser, ParseResult, MediaInfo
from ..media_handler import MediaHandler

# Standalone script for Playwright extraction (runs in subprocess)
_PW_SCRIPT = '''
import sys, json
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = context.new_page()
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector(
                "article, main, [role=main], .content, .markdown, .docs-content, .vp-doc, #__next, #__nuxt, #app",
                timeout=5000
            )
        except:
            pass
        page.wait_for_timeout(3000)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        browser.close()
        sys.exit(0)
    
    title = page.title() or "Untitled"
    
    rendered = page.evaluate("""() => {
        const sels = [
            "article", "main", "[role=main]",
            ".vp-doc", ".docs-content", ".markdown-body", ".prose",
            ".theme-default-content", ".page-content", ".nextra-content",
            "#__next main", "#__nuxt main", "#app main",
            ".content", ".article", ".post-content", ".entry-content"
        ];
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el && el.innerText.trim().length > 100) return el.outerHTML;
        }
        const body = document.body.cloneNode(true);
        body.querySelectorAll("script,style,noscript,iframe,svg").forEach(e => e.remove());
        body.querySelectorAll("nav,header,footer,aside").forEach(e => e.remove());
        return body.innerHTML;
    }""")
    
    full_html = page.content()
    browser.close()
    
    print(json.dumps({"title": title, "rendered": rendered, "full_html_len": len(full_html)}))
'''


class DynamicParser(BaseParser):
    """Dynamic fallback using headless browser (Playwright) in a subprocess"""

    def can_handle(self, url: str) -> bool:
        return True

    def parse(self, url: str) -> ParseResult:
        try:
            print(f"    [Dynamic] Starting Playwright subprocess for: {url[:60]}...")

            # Run Playwright in a subprocess to avoid event loop conflicts
            result = subprocess.run(
                [sys.executable, "-c", _PW_SCRIPT, url],
                capture_output=True, text=True, timeout=50,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin",
                     "HOME": "/root",
                     "REQUESTS_CA_BUNDLE": "/etc/ssl/certs/ca-certificates.crt",
                     "SSL_CERT_FILE": "/etc/ssl/certs/ca-certificates.crt"}
            )

            if result.returncode != 0:
                err = result.stderr.strip()[-200:]
                print(f"    [Dynamic] Subprocess failed: {err}")
                return ParseResult(success=False, error=f"Playwright subprocess error: {err}")

            data = json.loads(result.stdout.strip())

            if "error" in data:
                print(f"    [Dynamic] Navigation error: {data['error']}")
                return ParseResult(success=False, error=data["error"])

            title = data["title"]
            rendered_html = data["rendered"]

            print(f"    [Dynamic] Rendered content: {len(rendered_html)} chars")

            if not rendered_html or len(rendered_html.strip()) < 50:
                return ParseResult(success=False, error="No rendered content found")

            # Initialize media handler
            media_handler = MediaHandler(base_url=url)

            # Parse the rendered content
            soup = BeautifulSoup(rendered_html, 'lxml')
            soup = self.clean_html(soup)
            content = soup.find('body') or soup

            # Download and cache images
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            content, image_map = media_handler.process_images_in_soup(content, headers)

            # Convert to markdown
            markdown_content = md(str(content), heading_style="ATX")
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = markdown_content.strip()

            if len(markdown_content) < 50:
                return ParseResult(success=False, error="Content extraction too short")

            full_markdown = f"# {title}\n\n{markdown_content}"
            markdown_with_local = media_handler.get_markdown_with_local_images(full_markdown, image_map)

            media_info = MediaInfo(
                images=image_map,
                videos=[]
            )

            return ParseResult(
                success=True,
                title=title,
                markdown=full_markdown,
                markdown_with_local_images=markdown_with_local,
                media=media_info
            )

        except subprocess.TimeoutExpired:
            print(f"    [Dynamic] Subprocess timeout (50s)")
            return ParseResult(success=False, error="Playwright timed out")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ParseResult(success=False, error=f"Dynamic parse error: {str(e)}")

    def _extract_main_content(self, soup):
        """Heuristic detection of article body"""
        import re as _re
        selectors = [
            ('div', {'class_': _re.compile(r'vp-doc|docs-content|markdown-body|prose|nextra')}),
            ('div', {'class_': _re.compile(r'theme-default-content|page-content')}),
            ('article', {}),
            ('main', {}),
            ('div', {'class_': _re.compile(r'^content$|^article$|^post$|^entry')}),
            ('div', {'id': _re.compile(r'^content$|^main$|^article$')}),
            ('div', {'role': 'main'}),
        ]

        for tag, attrs in selectors:
            content = soup.find(tag, **attrs)
            if content and len(content.get_text(strip=True)) > 100:
                return content

        best = None
        best_len = 0
        for div in soup.find_all('div'):
            text = div.get_text(strip=True)
            if len(text) > best_len and len(text) > 200:
                children_divs = div.find_all('div', recursive=False)
                if len(children_divs) < 20:
                    best = div
                    best_len = len(text)

        return best
