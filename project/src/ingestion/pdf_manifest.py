"""PDF manifest and page-level operations using PyMuPDF."""
import json
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from ..core.logging import get_logger
from ..core import paths

log = get_logger(__name__)


class PDFManifest:
    """Manages page-level access and metadata for the gauntlet PDF."""

    def __init__(self, pdf_path: Optional[Path] = None):
        self.pdf_path = pdf_path or paths.GAUNTLET_PDF
        self._doc = None
        self._page_count = 0

    def open(self):
        self._doc = fitz.open(str(self.pdf_path))
        self._page_count = len(self._doc)
        log.info(f"Opened PDF with {self._page_count} pages")

    def close(self):
        if self._doc:
            self._doc.close()

    @property
    def page_count(self) -> int:
        return self._page_count

    def get_page_text(self, page_num: int) -> str:
        """Extract text from a 1-indexed page number."""
        if not self._doc:
            self.open()
        page = self._doc[page_num - 1]  # fitz is 0-indexed
        return page.get_text("text")

    def get_page_text_blocks(self, page_num: int) -> list:
        """Get structured text blocks from a page."""
        if not self._doc:
            self.open()
        page = self._doc[page_num - 1]
        return page.get_text("blocks")

    def render_page_image(self, page_num: int, dpi: int = 200) -> Path:
        """Render a page to PNG image. Returns path."""
        if not self._doc:
            self.open()
        out_path = paths.RENDERED / f"page_{page_num:04d}.png"
        if out_path.exists():
            return out_path
        page = self._doc[page_num - 1]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(out_path))
        return out_path

    def extract_all_text(self) -> dict[int, str]:
        """Extract text from all pages. Returns {page_num: text}."""
        if not self._doc:
            self.open()
        result = {}
        for i in range(self._page_count):
            page_num = i + 1
            result[page_num] = self._doc[i].get_text("text")
        return result

    def build_manifest(self) -> list[dict]:
        """Build a page manifest with basic metadata."""
        if not self._doc:
            self.open()
        manifest = []
        for i in range(self._page_count):
            page_num = i + 1
            page = self._doc[i]
            text = page.get_text("text")
            manifest.append({
                "page_num": page_num,
                "char_count": len(text),
                "word_count": len(text.split()),
                "has_text": len(text.strip()) > 10,
            })
        # Save manifest
        manifest_path = paths.PARSED / "page_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        log.info(f"Built manifest for {len(manifest)} pages")
        return manifest

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
