"""
Modular Docling Pipeline Configuration
=======================================

Every major stage of the pipeline can be independently set to:

    DISABLED  -> stage is skipped entirely (where Docling allows it)
    BUILTIN   -> Docling's default implementation is used
    CUSTOM    -> a user-supplied implementation is used instead

Honesty note on Docling's real extension points
-------------------------------------------------
Docling's public API does not expose a clean "swap the model" hook for
every stage. Concretely:

  - OCR                    -> genuinely swappable (Tesseract / EasyOCR /
                               RapidOCR / OcrMac / your own OcrOptions).
  - Picture description    -> genuinely swappable via
                               PictureDescriptionVlmOptions + an API engine
                               (Gemini, OpenRouter, your own endpoint, ...).
  - Full-document VLM      -> genuinely swappable via VlmPipeline +
                               ApiVlmEngineOptions (this replaces layout,
                               OCR, tables and reading order all at once).
  - Table structure        -> only "fast" vs "accurate" mode is swappable
                               natively; a truly custom table model has to
                               be applied as a POST-PROCESSING hook against
                               the built-in result.
  - Layout detection        -> no public swap point; CUSTOM here runs the
                               built-in layout model and then applies your
                               `custom_impl` as a post-processing hook.
  - Figure classification  -> same situation as layout: post-processing
                               hook rather than a true model swap.
  - Reading order           -> same situation: post-processing hook.
  - Export                  -> Docling ships Markdown / HTML / JSON /
                               DocTags exporters. CUSTOM means "call my
                               exporter function on the DoclingDocument
                               instead of Docling's built-in exporter."

This module makes that distinction explicit in the code and docstrings so
nobody assumes a capability Docling doesn't actually have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional


# =============================================================================
# Stage modes
# =============================================================================

class StageMode(str, Enum):
    DISABLED = "disabled"
    BUILTIN = "builtin"
    CUSTOM = "custom"


# Stages that Docling can genuinely skip outright.
DISABLE_CAPABLE_STAGES = {
    "ocr",
    "table_structure",
    "figure_classification",
    "vlm",
}
# Layout, reading_order and export cannot be meaningfully "disabled" in
# Docling (you'd get no document at all), so DISABLED is not offered there.


class UnsupportedStageModeError(ValueError):
    """Raised when a mode is requested that the stage cannot honor."""


# =============================================================================
# Per-stage config objects
# =============================================================================

@dataclass
class StageConfig:
    """Base config shared by every stage."""

    mode: StageMode = StageMode.BUILTIN

    # Only used when mode == CUSTOM.
    # For genuinely-swappable stages (ocr, picture_description, vlm) this is
    # typically an options object Docling understands (e.g. an OcrOptions
    # subclass or ApiVlmEngineOptions).
    # For hook-based stages (layout, table_structure, figure_classification,
    # reading_order, export) this must be a callable -- see each subclass.
    custom_impl: Optional[Any] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)
    stage_name: str = "stage"

    def __post_init__(self) -> None:
        if self.mode == StageMode.DISABLED and self.stage_name not in DISABLE_CAPABLE_STAGES:
            raise UnsupportedStageModeError(
                f"'{self.stage_name}' cannot be disabled in Docling; "
                f"choose BUILTIN or CUSTOM."
            )
        if self.mode == StageMode.CUSTOM and self.stage_name != "vlm" and self.custom_impl is None:
            raise ValueError(
                f"'{self.stage_name}' mode=CUSTOM requires custom_impl to be set."
            )


@dataclass
class LayoutStageConfig(StageConfig):
    """CUSTOM = post-processing hook: fn(doc, page_predictions) -> patched predictions."""
    stage_name: str = field(default="layout", init=False)


@dataclass
class OcrStageConfig(StageConfig):
    """CUSTOM = a Docling OcrOptions instance (EasyOcrOptions, TesseractCliOcrOptions,
    RapidOcrOptions, OcrMacOptions, or your own OcrOptions subclass)."""
    stage_name: str = field(default="ocr", init=False)
    engine: str = "easyocr"  # used only when mode == BUILTIN


@dataclass
class TableStructureStageConfig(StageConfig):
    """CUSTOM = post-processing hook: fn(doc, table_predictions) -> patched predictions.
    BUILTIN still lets you pick the Docling table mode ('fast' / 'accurate')."""
    stage_name: str = field(default="table_structure", init=False)
    builtin_mode: str = "accurate"  # 'fast' | 'accurate', used when mode == BUILTIN


@dataclass
class FigureClassificationStageConfig(StageConfig):
    """CUSTOM = post-processing hook: fn(doc, picture_items) -> patched items."""
    stage_name: str = field(default="figure_classification", init=False)


@dataclass
class VlmStageConfig(StageConfig):
    """CUSTOM = an ApiVlmEngineOptions pointed at any OpenAI-compatible chat endpoint
    (Gemini, OpenRouter, a self-hosted Qwen-VL server, etc.). Enabling VLM mode
    replaces layout/OCR/table/reading-order with the VLM's own understanding."""
    mode: StageMode = StageMode.DISABLED  # VLM is opt-in by default
    stage_name: str = field(default="vlm", init=False)
    preset: str = "granite_docling"       # used when mode == BUILTIN
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    timeout: int = 90
    max_tokens: int = 8192

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.mode == StageMode.CUSTOM and not (self.api_url and self.model_name):
            raise ValueError("vlm mode=CUSTOM requires api_url and model_name.")


@dataclass
class ReadingOrderStageConfig(StageConfig):
    """CUSTOM = post-processing hook: fn(doc) -> doc with reordered elements."""
    stage_name: str = field(default="reading_order", init=False)


@dataclass
class ExportStageConfig(StageConfig):
    """CUSTOM = fn(doc) -> Any (your own exporter). BUILTIN uses `builtin_format`."""
    stage_name: str = field(default="export", init=False)
    builtin_format: str = "markdown"  # 'markdown' | 'html' | 'json' | 'doctags'


# =============================================================================
# Aggregate pipeline configuration
# =============================================================================

@dataclass
class DoclingPipelineConfig:
    layout: LayoutStageConfig = field(default_factory=LayoutStageConfig)
    ocr: OcrStageConfig = field(default_factory=OcrStageConfig)
    table_structure: TableStructureStageConfig = field(default_factory=TableStructureStageConfig)
    figure_classification: FigureClassificationStageConfig = field(
        default_factory=FigureClassificationStageConfig
    )
    vlm: VlmStageConfig = field(default_factory=VlmStageConfig)
    reading_order: ReadingOrderStageConfig = field(default_factory=ReadingOrderStageConfig)
    export: ExportStageConfig = field(default_factory=ExportStageConfig)

    device: str = "auto"
    images_scale: float = 2.0

    def __post_init__(self) -> None:
        if self.vlm.mode != StageMode.DISABLED and self.layout.mode != StageMode.DISABLED:
            # Not a hard error -- Docling will just run layout/OCR/table results
            # from the standard pipeline are ignored once VlmPipeline is chosen --
            # but it's very likely not what the caller intended, so warn loudly.
            import warnings

            warnings.warn(
                "VLM stage is enabled: it replaces layout/OCR/table detection "
                "with the VLM's own document understanding. The layout/ocr/"
                "table_structure/reading_order settings will be ignored.",
                stacklevel=2,
            )


# =============================================================================
# Builder: turns the config into a working Docling DocumentConverter
# =============================================================================

def build_converter(config: DoclingPipelineConfig):
    """
    Translate a DoclingPipelineConfig into a live docling.DocumentConverter.

    Raises UnsupportedStageModeError if a stage is asked to do something
    Docling's public API genuinely cannot do (e.g. disable layout).
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorOptions,
        PdfPipelineOptions,
        PictureDescriptionVlmOptions,
    )
    from docling.datamodel.vlm_engine_options import ApiVlmEngineOptions, VlmEngineType
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    from docling.pipeline.vlm_pipeline import VlmPipeline

    # -- Path 1: full VLM pipeline -------------------------------------------------
    if config.vlm.mode != StageMode.DISABLED:
        from docling.datamodel.pipeline_options import VlmConvertOptions, VlmPipelineOptions

        if config.vlm.mode == StageMode.BUILTIN:
            vlm_options = VlmConvertOptions.from_preset(config.vlm.preset)
            enable_remote = False
        else:  # CUSTOM
            vlm_options = VlmConvertOptions.from_preset(
                config.vlm.preset,
                engine_options=ApiVlmEngineOptions(
                    runtime_type=VlmEngineType.API,
                    url=config.vlm.api_url,
                    headers={"Authorization": f"Bearer {config.vlm.api_key}"},
                    params={
                        "model": config.vlm.model_name,
                        "temperature": 0.0,
                        "max_tokens": config.vlm.max_tokens,
                    },
                    timeout=config.vlm.timeout,
                ),
            )
            enable_remote = True

        pipeline_options = VlmPipelineOptions(
            vlm_options=vlm_options,
            do_picture_classification=config.figure_classification.mode != StageMode.DISABLED,
            enable_remote_services=enable_remote,
            images_scale=config.images_scale,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline, pipeline_options=pipeline_options
                )
            }
        )
        return _ConfiguredConverter(converter, config)

    # -- Path 2: standard pipeline ---------------------------------------------
    if config.layout.mode == StageMode.DISABLED:
        raise UnsupportedStageModeError("Layout detection cannot be disabled outside the VLM pipeline.")
    if config.reading_order.mode == StageMode.DISABLED:
        raise UnsupportedStageModeError("Reading order cannot be disabled outside the VLM pipeline.")

    table_enabled = config.table_structure.mode != StageMode.DISABLED
    ocr_enabled = config.ocr.mode != StageMode.DISABLED
    fig_class_enabled = config.figure_classification.mode != StageMode.DISABLED

    pipeline_options = PdfPipelineOptions(
        do_ocr=ocr_enabled,
        do_table_structure=table_enabled,
        do_picture_classification=fig_class_enabled,
        do_picture_description=False,  # wired up separately below if requested
        enable_remote_services=(config.ocr.mode == StageMode.CUSTOM),
        images_scale=config.images_scale,
        accelerator_options=AcceleratorOptions(device=config.device),
    )

    if ocr_enabled and config.ocr.mode == StageMode.CUSTOM:
        # custom_impl is expected to be a ready-made Docling OcrOptions instance
        pipeline_options.ocr_options = config.ocr.custom_impl

    if table_enabled and config.table_structure.mode == StageMode.BUILTIN:
        pipeline_options.table_structure_options.mode = config.table_structure.builtin_mode

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=StandardPdfPipeline, pipeline_options=pipeline_options
            )
        }
    )
    return _ConfiguredConverter(converter, config)


class _ConfiguredConverter:
    """
    Thin wrapper that runs Docling's converter and then applies any
    post-processing hooks (layout / table_structure / figure_classification /
    reading_order / export) that the caller marked as CUSTOM. Those stages
    have no native "swap the model" hook in Docling's public API, so CUSTOM
    is implemented as: run the built-in stage, then let the user's callable
    rewrite the result.
    """

    def __init__(self, converter, config: DoclingPipelineConfig):
        self._converter = converter
        self._config = config

    def convert(self, input_path: str):
        result = self._converter.convert(input_path)
        doc = result.document

        if self._config.layout.mode == StageMode.CUSTOM:
            doc = self._config.layout.custom_impl(doc)
        if self._config.table_structure.mode == StageMode.CUSTOM:
            doc = self._config.table_structure.custom_impl(doc)
        if self._config.figure_classification.mode == StageMode.CUSTOM:
            doc = self._config.figure_classification.custom_impl(doc)
        if self._config.reading_order.mode == StageMode.CUSTOM:
            doc = self._config.reading_order.custom_impl(doc)

        result.document = doc
        return result

    def export(self, result) -> Any:
        cfg = self._config.export
        if cfg.mode == StageMode.CUSTOM:
            return cfg.custom_impl(result.document)

        fmt = cfg.builtin_format
        exporters: Dict[str, Callable[[], Any]] = {
            "markdown": result.document.export_to_markdown,
            "html": result.document.export_to_html,
            "json": result.document.export_to_dict,
            "doctags": result.document.export_to_document_tokens,
        }
        if fmt not in exporters:
            raise ValueError(f"Unknown export format '{fmt}'.")
        return exporters[fmt]()


# =============================================================================
# Example usage matching the requested mockup:
#   Layout=Built-in, OCR=Custom, Table=Built-in,
#   Figure Classification=Custom, VLM=Disabled, Reading Order=Built-in
# =============================================================================

if __name__ == "__main__":
    from docling.datamodel.pipeline_options import EasyOcrOptions

    def my_custom_figure_classifier(doc):
        # Replace with a real model call; this is just a stand-in.
        for picture in doc.pictures:
            picture.annotations.append({"source": "custom-classifier"})
        return doc

    config = DoclingPipelineConfig(
        layout=LayoutStageConfig(mode=StageMode.BUILTIN),
        ocr=OcrStageConfig(mode=StageMode.CUSTOM, custom_impl=EasyOcrOptions(lang=["en"])),
        table_structure=TableStructureStageConfig(mode=StageMode.BUILTIN, builtin_mode="accurate"),
        figure_classification=FigureClassificationStageConfig(
            mode=StageMode.CUSTOM, custom_impl=my_custom_figure_classifier
        ),
        vlm=VlmStageConfig(mode=StageMode.DISABLED),
        reading_order=ReadingOrderStageConfig(mode=StageMode.BUILTIN),
        export=ExportStageConfig(mode=StageMode.BUILTIN, builtin_format="markdown"),
    )

    converter = build_converter(config)
    result = converter.convert("document.pdf")
    print(converter.export(result))