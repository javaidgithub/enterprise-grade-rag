# import logging
# import os
# from pathlib import Path

# from dotenv import load_dotenv

# from docling.datamodel.base_models import InputFormat
# from docling.datamodel.pipeline_options import (
#     VlmConvertOptions,
#     VlmPipelineOptions,
# )
# from docling.datamodel.vlm_engine_options import (
#     ApiVlmEngineOptions,
#     VlmEngineType,
# )
# from docling.document_converter import DocumentConverter, PdfFormatOption
# from docling.pipeline.vlm_pipeline import VlmPipeline

# # ---------------------------------------------------------------------------
# # Logging setup
# # ---------------------------------------------------------------------------
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
# )
# logger = logging.getLogger("gemini_docling")

# # Turn up Docling's own internal loggers so you see per-page / per-request detail.
# logging.getLogger("docling").setLevel(logging.DEBUG)

# # Turn up the HTTP client so you can see the actual request going out and the
# # raw response coming back from Gemini (status code, body, etc.).
# logging.getLogger("httpx").setLevel(logging.DEBUG)
# logging.getLogger("urllib3").setLevel(logging.DEBUG)

# # ---------------------------------------------------------------------------
# # Step 1: load credentials
# # ---------------------------------------------------------------------------
# logger.info("Loading environment variables...")
# load_dotenv()

# api_key = os.getenv("GEMINI_API_KEY")
# if not api_key:
#     logger.error("GEMINI_API_KEY not found in environment / .env file.")
#     raise RuntimeError("GEMINI_API_KEY not set (check your .env file).")
# logger.info("GEMINI_API_KEY loaded (length=%d).", len(api_key))

# # ---------------------------------------------------------------------------
# # Step 2: build VLM engine options
# # ---------------------------------------------------------------------------
# logger.info("Building VLM engine options (Gemini, OpenAI-compatible endpoint)...")
# try:
#     vlm_options = VlmConvertOptions.from_preset(
#         "granite_docling",
#         engine_options=ApiVlmEngineOptions(
#             runtime_type=VlmEngineType.API,
#             url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
#             headers={
#                 "Content-Type": "application/json",
#                 "Authorization": f"Bearer {api_key}",
#             },
#             params={
#                 "model": "gemini-3.5-flash",
#                 "temperature": 0.0,
#                 "max_tokens": 8192,
#             },
#             timeout=120,
#         ),
#     )
#     logger.info("VLM engine options built successfully.")
# except Exception:
#     logger.exception("Failed while building VlmConvertOptions.")
#     raise

# # ---------------------------------------------------------------------------
# # Step 3: build pipeline options
# # ---------------------------------------------------------------------------
# logger.info("Building VLM pipeline options...")
# try:
#     pipeline_options = VlmPipelineOptions(
#         vlm_options=vlm_options,
#         enable_remote_services=True,
#     )
#     logger.info("Pipeline options built successfully.")
# except Exception:
#     logger.exception("Failed while building VlmPipelineOptions.")
#     raise

# # ---------------------------------------------------------------------------
# # Step 4: build the converter
# # ---------------------------------------------------------------------------
# logger.info("Building DocumentConverter...")
# try:
#     doc_converter = DocumentConverter(
#         format_options={
#             InputFormat.PDF: PdfFormatOption(
#                 pipeline_options=pipeline_options,
#                 pipeline_cls=VlmPipeline,
#             )
#         }
#     )
#     logger.info("DocumentConverter built successfully.")
# except Exception:
#     logger.exception("Failed while building DocumentConverter.")
#     raise

# # ---------------------------------------------------------------------------
# # Step 5: check the input file exists before we even try converting
# # ---------------------------------------------------------------------------
# input_doc_path = Path("sample.pdf")
# logger.info("Checking input file: %s", input_doc_path.resolve())
# if not input_doc_path.exists():
#     logger.error("Input file does not exist: %s", input_doc_path.resolve())
#     raise FileNotFoundError(f"No such file: {input_doc_path.resolve()}")
# logger.info("Input file found (%d bytes).", input_doc_path.stat().st_size)

# # ---------------------------------------------------------------------------
# # Step 6: run the conversion
# # ---------------------------------------------------------------------------
# logger.info("Starting conversion...")
# try:
#     result = doc_converter.convert(input_doc_path)
#     logger.info("Conversion call returned. Exporting to markdown...")
#     markdown = result.document.export_to_markdown()
#     logger.info("Export complete (%d characters).", len(markdown))
#     print(markdown)
# except Exception:
#     logger.exception("Conversion failed.")
#     raise
# finally:
#     import gc

#     logger.info("Cleaning up converter before interpreter shutdown...")
#     del doc_converter
#     gc.collect()
#     logger.info("Done.")


import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from docling.datamodel.base_models import InputFormat 
from docling.datamodel.pipeline_options import ResponseFormat
from docling.datamodel.pipeline_options import (
    VlmConvertOptions,
    VlmPipelineOptions,
)
from docling.datamodel.vlm_engine_options import (
    ApiVlmEngineOptions,
    VlmEngineType,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("gemini_docling")
logging.getLogger("docling").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not set (check your .env file).")

logger.info("Building VLM engine options with MARKDOWN response format (not DocTags)...")

vlm_options = VlmConvertOptions(
    engine_options=ApiVlmEngineOptions(
        runtime_type=VlmEngineType.API,
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        params={
            "model": "gemini-3.5-flash",
            "temperature": 0.0,
            "max_tokens": 8192,
        },
        timeout=120,
    ),
    model_spec={
        "name": "Gemini Flash (Markdown OCR)",
        "default_repo_id": "gemini-3.5-flash",
        "prompt": (
            "Convert this document page to markdown. Preserve headings, "
            "tables, lists, and reading order exactly as they appear. "
            "Output only the markdown, with no commentary or code fences."
        ),
        "response_format": ResponseFormat.MARKDOWN,
        "max_new_tokens": 8192,
        "temperature": 0.0,
    },
    scale=2.0,
)

pipeline_options = VlmPipelineOptions(
    vlm_options=vlm_options,
    enable_remote_services=True,
)

doc_converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
            pipeline_cls=VlmPipeline,
        )
    }
)

input_doc_path = Path("sample.pdf")
logger.info("Starting conversion with MARKDOWN response format...")

try:
    result = doc_converter.convert(input_doc_path)
    markdown = result.document.export_to_markdown()
    logger.info("Export complete (%d characters).", len(markdown))
    print(markdown)
except Exception:
    logger.exception("Conversion failed.")
    raise
# finally:
#     import gc
#     del doc_converter
#     gc.collect()