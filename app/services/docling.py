"""
Enterprise Pure-Docling Document Parsing Service.
Python port of src/services/docling.ts -- now backed entirely by the
`docling` library instead of a custom Gemini + PyMuPDF pipeline.

Figure extraction strategy:
  - Docling's own conversion pipeline extracts every detected picture with
    its real page number and bounding box, and renders a cropped PNG for
    each one directly (generate_picture_images=True) -- no manual PyMuPDF
    crop code needed.
  - Titles/descriptions for figures come from Docling's built-in
    picture-description enrichment (a local vision-language model that
    runs inside the pipeline), so there are no external API calls
    (e.g. Gemini) anywhere in this file.

Table extraction strategy:
  - Docling's table-structure model (TableFormer) detects tables across
    all supported formats and exposes them as TableItem objects that
    export directly to Markdown, with row/column counts on the item.

Supported formats: PDF, DOCX, PPTX, XLSX, HTML, images (PNG/JPG/TIFF/BMP).
Plain-text formats (TXT/CSV/MD/JSON) are treated as raw text, same as the
original fallback behavior.

NOTE ON DEPENDENCIES:
  pip install docling
  Picture captioning uses PictureDescriptionVlmOptions, which downloads a
  small local vision-language model (SmolVLM-256M) on first use. If you'd
  rather not pay that cost, set `do_picture_description=False` below --
  figures will still get real page/bbox/crop, just a generic title.
"""

import logging
import os
import random
import string
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    PictureDescriptionVlmOptions,
    RapidOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

logger = logging.getLogger(__name__)

TEXT_FILE_TYPES = {"txt", "csv", "md", "json"}

# Root directory where cropped figure PNGs are saved, namespaced per document.
FIGURES_OUTPUT_DIR = "figures"

# Formats docling's DocumentConverter can natively ingest.
DOCLING_SUPPORTED_TYPES = {
    "pdf", "docx", "pptx", "xlsx", "html", "htm",
    "png", "jpg", "jpeg", "tif", "tiff", "bmp",
}


@dataclass
class ExtractedTable:
    id: str
    title: str
    markdown: str
    rowCount: int
    colCount: int


@dataclass
class ExtractedFigure:
    id: str
    title: str
    description: str
    page: Optional[int] = None
    # [x1, y1, x2, y2]
    boundingBox: Optional[List[float]] = None
    imageLink: Optional[str] = None
    base64Image: Optional[str] = None


@dataclass
class ParsedDocument:
    documentId: str
    fileName: str
    fileType: str
    rawText: str
    structuredMarkdown: str
    tables: List[ExtractedTable]
    figures: List[ExtractedFigure]
    metadata: Dict[str, Any]
    createdAt: str

    def to_dict(self) -> dict:
        return {**asdict(self)}


class DoclingService:
    """
    Main parsing service supporting PDF, DOCX, PPTX, XLSX, CSV, TXT, HTML, MD, Images.
    Fully backed by the open-source `docling` library -- no external LLM calls.
    """

    # Building a converter loads OCR + table + picture-description models,
    # which is expensive -- build once, reuse across every parse_document call.
    _converter: Optional[DocumentConverter] = None

    @classmethod
    def _get_converter(cls) -> DocumentConverter:
        if cls._converter is not None:
            return cls._converter

        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            ocr_options=RapidOcrOptions(),
            do_table_structure=True,
            generate_picture_images=True,
            images_scale=2.0,
            do_picture_description=False,
            picture_description_options=PictureDescriptionVlmOptions(
                repo_id="HuggingFaceTB/SmolVLM-256M-Instruct",
                prompt=(
                    "Describe this figure/image in detail for a document "
                    "index, including any data, labels, or trends it shows."
                ),
            ),
        )

        cls._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        return cls._converter

    @staticmethod
    def _generate_document_id() -> str:
        rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=9))
        return f"doc_{int(time.time() * 1000)}_{rand_suffix}"

    @staticmethod
    def _item_caption_text(item) -> Optional[str]:
        """Docling captions are RefItems resolved against the doc; fetch text safely."""
        try:
            if item.captions:
                cap = item.captions[0]
                text = getattr(cap, "text", None)
                if text:
                    return text
        except Exception:
            pass
        return None

    @classmethod
    def _extract_tables(cls, doc) -> List[ExtractedTable]:
        tables: List[ExtractedTable] = []
        for i, table in enumerate(doc.tables):
            try:
                markdown = table.export_to_markdown(doc=doc)
            except Exception as error:
                logger.warning("[DoclingService] Failed exporting table %d: %s", i, error)
                markdown = ""

            n_rows = getattr(table.data, "num_rows", 0) if table.data else 0
            n_cols = getattr(table.data, "num_cols", 0) if table.data else 0

            title = cls._item_caption_text(table) or f"Table {i + 1}"

            tables.append(
                ExtractedTable(
                    id=f"table_{i}",
                    title=title,
                    markdown=markdown,
                    rowCount=n_rows,
                    colCount=n_cols,
                )
            )
        return tables

    @classmethod
    def _extract_figures(cls, doc, document_id: str) -> List[ExtractedFigure]:
        output_dir = os.path.join(FIGURES_OUTPUT_DIR, document_id)
        os.makedirs(output_dir, exist_ok=True)

        figures: List[ExtractedFigure] = []
        for i, picture in enumerate(doc.pictures):
            fig_id = f"fig_{i}"

            page_no = None
            bbox = None
            if picture.prov:
                prov = picture.prov[0]
                page_no = prov.page_no
                rect = prov.bbox
                bbox = [rect.l, rect.t, rect.r, rect.b]

            image_link = None
            try:
                pil_image = picture.get_image(doc)
                if pil_image is not None:
                    filepath = os.path.join(output_dir, f"{fig_id}.png")
                    pil_image.save(filepath)
                    image_link = filepath
            except Exception as error:
                logger.warning(
                    "[DoclingService] Could not save crop for figure %d: %s", i, error
                )

            # Populated by the picture-description enrichment step
            # (do_picture_description=True) as an annotation on the item.
            description = "No description extracted"
            try:
                for annotation in picture.annotations:
                    text = getattr(annotation, "text", None)
                    if text:
                        description = text
                        break
            except Exception:
                pass

            title = cls._item_caption_text(picture) or f"Figure {i + 1}"

            figures.append(
                ExtractedFigure(
                    id=fig_id,
                    title=title,
                    description=description,
                    page=page_no,
                    boundingBox=bbox,
                    imageLink=image_link,
                    base64Image=None,
                )
            )
        return figures

    @classmethod
    async def parse_document(
        cls,
        file_bytes: bytes,
        file_name: str,
        mime_type: str,
        api_key: Optional[str] = None,
    ) -> ParsedDocument:
        """
        `api_key` is kept only for backwards-compatible call signatures --
        it is no longer used. Parsing is 100% local via Docling.
        """
        file_type = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "unknown"
        document_id = cls._generate_document_id()

        logger.info("[DoclingService] Starting parsing for %s (%s)", file_name, mime_type)

        if file_type in TEXT_FILE_TYPES:
            try:
                raw_text = file_bytes.decode("utf-8", errors="replace")
            except Exception:
                raw_text = ""
            return cls._generate_text_document(document_id, file_name, file_type, raw_text)

        if file_type not in DOCLING_SUPPORTED_TYPES:
            return cls._generate_fallback_document(
                document_id,
                file_name,
                file_type,
                f"Unsupported file type for Docling: {file_type}. "
                f"Binary size: {len(file_bytes)} bytes.",
            )

        tmp_path: Optional[Path] = None
        try:
            suffix = f".{file_type}"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)

            converter = cls._get_converter()
            result = converter.convert(tmp_path)
            doc = result.document

            structured_markdown = doc.export_to_markdown()
            raw_text = (
                doc.export_to_text() if hasattr(doc, "export_to_text") else structured_markdown
            )

            tables = cls._extract_tables(doc)
            figures = cls._extract_figures(doc, document_id)

            page_count = len(doc.pages) if hasattr(doc, "pages") else None

            metadata = {
                "title": getattr(doc, "name", file_name),
                "author": None,
                "pageCount": page_count,
                "additional": {},
                "originalMimeType": mime_type,
                "fileSize": f"{(len(file_bytes) / 1024):.2f} KB",
            }

            return ParsedDocument(
                documentId=document_id,
                fileName=file_name,
                fileType=file_type,
                rawText=raw_text or "No text content extracted",
                structuredMarkdown=structured_markdown or "No markdown layout structured",
                tables=tables,
                figures=figures,
                metadata=metadata,
                createdAt=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as error:
            logger.error(
                "[DoclingService] Docling parsing failed. Falling back to raw text: %s", error
            )
            try:
                fallback_text = file_bytes.decode("utf-8", errors="replace")
            except Exception:
                fallback_text = (
                    f"Extracted text from binary document {file_name}. "
                    f"Size: {len(file_bytes)} bytes."
                )
            return cls._generate_fallback_document(document_id, file_name, file_type, fallback_text)

        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    pass  # Windows: a library still holds a handle on the temp file

    @classmethod
    def _generate_text_document(
        cls, document_id: str, file_name: str, file_type: str, raw_text: str
    ) -> ParsedDocument:
        tables: List[ExtractedTable] = []

        if file_type == "csv":
            rows = [r.split(",") for r in raw_text.split("\n") if r.strip()]
            if rows:
                headers = rows[0]
                md_lines = [
                    f"| {' | '.join(headers)} |",
                    f"| {' | '.join(['---'] * len(headers))} |",
                ]
                for row in rows[1:11]:
                    md_lines.append(f"| {' | '.join(row)} |")
                md = "\n".join(md_lines) + "\n"

                tables.append(
                    ExtractedTable(
                        id="table_0",
                        title="Imported CSV Table",
                        markdown=md,
                        rowCount=max(len(rows) - 1, 0),
                        colCount=len(headers),
                    )
                )

        return ParsedDocument(
            documentId=document_id,
            fileName=file_name,
            fileType=file_type,
            rawText=raw_text,
            structuredMarkdown=f"# {file_name}\n\n{raw_text}",
            tables=tables,
            figures=[],
            metadata={"title": file_name, "pageCount": 1, "textOnly": True},
            createdAt=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def _generate_fallback_document(
        cls, document_id: str, file_name: str, file_type: str, raw_text: str
    ) -> ParsedDocument:
        return ParsedDocument(
            documentId=document_id,
            fileName=file_name,
            fileType=file_type,
            rawText=raw_text,
            structuredMarkdown=f"# {file_name}\n\n{raw_text}",
            tables=[],
            figures=[],
            metadata={"title": file_name, "pageCount": 1, "fallbackMode": True},
            createdAt=datetime.now(timezone.utc).isoformat(),
        )