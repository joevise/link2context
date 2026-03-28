import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from .base_parser import BaseParser, ParseResult, MediaInfo
from ..media_handler import MediaHandler


class DynamicParser(BaseParser):
    """Dynamic fallback using headless browser (Playwright)"""

    def can_handle(self, url: str) -> bool:
        return True

    def parse(self, url: str) -> ParseResult:
        try:
            from playwright.sync_api import sync_playwright

            print(f"    [Dynamic] Starting Playwright for: {url[:60]}...")

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    # Wait for SPA content to render
                    try:
                        page.wait_for_selector(
                            'article, main, [role="main"], .content, .markdown, '
                            '.docs-content, .vp-doc, #__next, #__nuxt, #app',
                            timeout=5000
                        )
                    except:
                        pass
                    page.wait_for_timeout(3000)
                except Exception as nav_error:
                    print(f"    [Dynamic] Navigation error: {nav_error}")
                    browser.close()
                    return ParseResult(success=False, error=f"Navigation failed: {str(nav_error)}")

                title = page.title() or "Untitled"

                # Extract rendered DOM content via JS (not page.content())
                # This gets the actual rendered HTML after SPA hydration
                rendered_html = page.evaluate("""() => {
                    // Try to find main content container
                    const selectors = [
                        'article', 'main', '[role="main"]',
                        '.vp-doc', '.docs-content', '.markdown-body', '.prose',
                        '.theme-default-content', '.page-content', '.nextra-content',
                        '#__next main', '#__nuxt main', '#app main',
                        '.content', '.article', '.post-content', '.entry-content'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) {
                            return el.outerHTML;
                        }
                    }
                    // Fallback: get body but strip scripts
                    const body = document.body.cloneNode(true);
                    body.querySelectorAll('script, style, noscript, iframe, svg').forEach(el => el.remove());
                    body.querySelectorAll('nav, header, footer, aside').forEach(el => el.remove());
                    return body.innerHTML;
                }""")

                # Also get full page HTML for video/image detection
                full_html = page.content()

                print(f"    [Dynamic] Rendered content: {len(rendered_html)} chars")

                browser.close()

            if not rendered_html or len(rendered_html.strip()) < 50:
                return ParseResult(success=False, error="No rendered content found")

            # Initialize media handler
            media_handler = MediaHandler(base_url=url)

            # Detect videos from full HTML
            videos = media_handler.detect_videos(full_html, None)

            # Parse the rendered content
            soup = BeautifulSoup(rendered_html, 'lxml')

            # Clean the DOM
            soup = self.clean_html(soup)

            # Find the root content element
            content = soup.find('body') or soup

            # Download and cache images
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            content, image_map = media_handler.process_images_in_soup(content, headers)

            # Convert to markdown
            markdown_content = md(str(content), heading_style="ATX")

            # Clean up
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = markdown_content.strip()

            if len(markdown_content) < 50:
                return ParseResult(success=False, error="Content extraction too short")

            full_markdown = f"# {title}\n\n{markdown_content}"

            # Create version with local images
            markdown_with_local = media_handler.get_markdown_with_local_images(full_markdown, image_map)

            # Add videos
            markdown_with_local = media_handler.add_videos_to_markdown(markdown_with_local, videos)
            full_markdown = media_handler.add_videos_to_markdown(full_markdown, videos)

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
            import traceback
            traceback.print_exc()
            return ParseResult(success=False, error=f"Dynamic parse error: {str(e)}")

    def _extract_main_content(self, soup):
        """Heuristic detection of article body — SPA/docs site aware"""
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
