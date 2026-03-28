# link2context

URL → clean Markdown converter with image caching and video detection.

## Features
- **Static parsing** - fast requests-based HTML parsing
- **WeChat article support** - handles lazy-loading images, QR cleanup
- **Dynamic fallback** - Playwright headless browser for JS-heavy pages
- **Image caching** - downloads and caches all article images locally
- **Video detection** - detects embedded videos (YouTube, Bilibili, etc.)
- **Web UI** - dark-themed frontend for interactive use

## Quick Start

```bash
docker compose up -d --build
```

Service runs at `http://localhost:8000`

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/parse` | POST | Parse URL → Markdown |
| `/api/images/{filename}` | GET | Cached images |

### Parse URL
```bash
curl -X POST http://localhost:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "use_dynamic": false}'
```

## Deploy
```bash
python3 deploy.py
```
