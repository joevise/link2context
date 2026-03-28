import base64
import httpx
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

CACHE_DIR = Path(__file__).parent / "cache" / "images"


@dataclass
class OCRConfig:
    provider: str  # openai, claude, custom
    base_url: str
    api_key: str
    model: str
    prompt: str


@dataclass
class OCRResult:
    success: bool
    image_path: str
    text: Optional[str] = None
    error: Optional[str] = None


class OCRService:
    """AI-powered OCR service for image text recognition"""
    
    DEFAULT_PROMPT = """请识别这张图片中的所有文字内容。
要求：
1. 保持原有的格式和结构
2. 如果有标题、列表、表格等，请用Markdown格式输出
3. 如果图片中没有文字，请回复"[图片无文字内容]"
4. 只输出识别的内容，不要添加额外说明"""

    def __init__(self, config: OCRConfig):
        self.config = config
        self.prompt = config.prompt or self.DEFAULT_PROMPT
    
    def _get_image_base64(self, image_path: str) -> Optional[str]:
        """Convert image to base64"""
        # Handle local cache path
        if image_path.startswith('/api/images/'):
            filename = image_path.split('/api/images/')[-1]
            full_path = CACHE_DIR / filename
        else:
            full_path = Path(image_path)
        
        if not full_path.exists():
            return None
        
        with open(full_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _get_media_type(self, image_path: str) -> str:
        """Get image media type"""
        path = image_path.lower()
        if path.endswith('.png'):
            return 'image/png'
        elif path.endswith('.gif'):
            return 'image/gif'
        elif path.endswith('.webp'):
            return 'image/webp'
        else:
            return 'image/jpeg'
    
    async def recognize_image(self, image_path: str) -> OCRResult:
        """Recognize text in a single image"""
        try:
            image_base64 = self._get_image_base64(image_path)
            if not image_base64:
                return OCRResult(
                    success=False,
                    image_path=image_path,
                    error=f"Image not found: {image_path}"
                )
            
            media_type = self._get_media_type(image_path)
            
            if self.config.provider == 'openai':
                text = await self._call_openai(image_base64, media_type)
            elif self.config.provider == 'claude':
                text = await self._call_claude(image_base64, media_type)
            else:  # custom - use OpenAI-compatible API
                text = await self._call_openai(image_base64, media_type)
            
            return OCRResult(
                success=True,
                image_path=image_path,
                text=text
            )
        except Exception as e:
            return OCRResult(
                success=False,
                image_path=image_path,
                error=str(e)
            )
    
    async def recognize_images(self, image_paths: List[str]) -> List[OCRResult]:
        """Recognize text in multiple images"""
        results = []
        for path in image_paths:
            result = await self.recognize_image(path)
            results.append(result)
        return results
    
    async def _call_openai(self, image_base64: str, media_type: str) -> str:
        """Call OpenAI Vision API"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self.prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4096
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
    
    async def _call_claude(self, image_base64: str, media_type: str) -> str:
        """Call Claude Vision API"""
        url = f"{self.config.base_url.rstrip('/')}/messages"
        
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": self.prompt
                        }
                    ]
                }
            ]
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data['content'][0]['text']
