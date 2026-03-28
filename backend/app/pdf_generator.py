import os
import re
from pathlib import Path
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

CACHE_DIR = Path(__file__).parent / "cache" / "images"


class PDFGenerator:
    """Generate PDF from markdown content with embedded images"""
    
    _fonts_registered = False
    _font_name = 'Helvetica'
    
    def __init__(self):
        self.image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
        self._try_register_fonts()
    
    @classmethod
    def _try_register_fonts(cls):
        """Try to register a Chinese-supporting font"""
        if cls._fonts_registered:
            return
        
        cls._fonts_registered = True
        
        # Try macOS PingFang font
        font_candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        
        for font_path in font_candidates:
            if os.path.exists(font_path):
                try:
                    if font_path.endswith('.ttc'):
                        pdfmetrics.registerFont(TTFont('CJKFont', font_path, subfontIndex=0))
                    else:
                        pdfmetrics.registerFont(TTFont('CJKFont', font_path))
                    cls._font_name = 'CJKFont'
                    print(f"Registered font: {font_path}")
                    return
                except Exception as e:
                    print(f"Failed to register {font_path}: {e}")
                    continue
        
        print("No CJK font found, using Helvetica (Chinese may not display)")
    
    def generate_pdf(self, markdown_content: str, title: str = "Document") -> bytes:
        """Generate PDF using ReportLab"""
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab is not installed")
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        styles = getSampleStyleSheet()
        font_name = self._font_name
        
        # Define custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            fontName=font_name,
            fontSize=20,
            leading=26,
            spaceAfter=18,
            textColor=HexColor('#1a1a1a'),
        )
        
        h2_style = ParagraphStyle(
            'CustomH2',
            fontName=font_name,
            fontSize=15,
            leading=20,
            spaceBefore=14,
            spaceAfter=8,
            textColor=HexColor('#333333'),
        )
        
        h3_style = ParagraphStyle(
            'CustomH3',
            fontName=font_name,
            fontSize=12,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
            textColor=HexColor('#444444'),
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            fontName=font_name,
            fontSize=10,
            leading=15,
            spaceAfter=6,
            textColor=HexColor('#333333'),
        )
        
        link_style = ParagraphStyle(
            'LinkStyle',
            fontName=font_name,
            fontSize=9,
            leading=13,
            spaceAfter=6,
            textColor=HexColor('#0066cc'),
            backColor=HexColor('#f5f5f5'),
            leftIndent=8,
            rightIndent=8,
        )
        
        story = []
        lines = markdown_content.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                story.append(Spacer(1, 4))
                continue
            
            if stripped == '---':
                story.append(Spacer(1, 12))
                continue
            
            # Headers
            if stripped.startswith('# '):
                text = self._clean_text(stripped[2:])
                if text:
                    story.append(Paragraph(text, title_style))
                continue
            
            if stripped.startswith('## '):
                text = self._clean_text(stripped[3:])
                if text:
                    story.append(Paragraph(text, h2_style))
                continue
            
            if stripped.startswith('### '):
                text = self._clean_text(stripped[4:])
                if text:
                    story.append(Paragraph(text, h3_style))
                continue
            
            # Images
            img_match = self.image_pattern.search(stripped)
            if img_match:
                img_path = img_match.group(2)
                if '/api/images/' in img_path:
                    filename = img_path.split('/api/images/')[-1]
                    local_path = CACHE_DIR / filename
                    if local_path.exists():
                        try:
                            img = RLImage(str(local_path))
                            max_w, max_h = 14*cm, 16*cm
                            ratio = min(max_w/img.drawWidth, max_h/img.drawHeight, 1)
                            img.drawWidth *= ratio
                            img.drawHeight *= ratio
                            story.append(Spacer(1, 6))
                            story.append(img)
                            story.append(Spacer(1, 6))
                        except Exception as e:
                            print(f"Image error: {e}")
                continue
            
            # Video links
            if '[Video]' in stripped or 'video' in stripped.lower():
                link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', stripped)
                if link_match:
                    url = link_match.group(2)
                    text = f"Video: {url}"
                    story.append(Paragraph(self._clean_text(text), link_style))
                    continue
            
            # Regular text
            text = self._clean_text(stripped)
            if text:
                story.append(Paragraph(text, body_style))
        
        try:
            doc.build(story)
        except Exception as e:
            print(f"Build error: {e}")
            # Minimal fallback
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = [
                Paragraph("Document", styles['Title']),
                Spacer(1, 20),
                Paragraph("Content could not be rendered. Please download as Markdown.", styles['Normal'])
            ]
            doc.build(story)
        
        result = buffer.getvalue()
        buffer.close()
        return result
    
    def _clean_text(self, text: str) -> str:
        """Clean and escape text for PDF"""
        if not text:
            return ""
        
        # Escape XML
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        
        # Filter characters
        result = []
        for char in text:
            code = ord(char)
            if code < 128:  # ASCII
                result.append(char)
            elif 0x4E00 <= code <= 0x9FFF:  # Chinese
                result.append(char)
            elif 0x3000 <= code <= 0x303F:  # CJK punctuation
                result.append(char)
            elif 0xFF00 <= code <= 0xFFEF:  # Fullwidth
                result.append(char)
            elif 0x3400 <= code <= 0x4DBF:  # CJK Ext A
                result.append(char)
            elif char in '，。！？、；：""''（）【】《》—…·':
                result.append(char)
            # Skip emoji and other special chars
        
        return ''.join(result)
