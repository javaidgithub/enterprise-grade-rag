import os
import sys
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    PictureDescriptionApiOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

class GeminiDocConverter:
    _converter = None

    @classmethod
    def _get_converter(cls) -> DocumentConverter:
        if cls._converter is not None:
            return cls._converter

        # Fetch API key from environment
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_api_key:
            print("[Warning]: GEMINI_API_KEY environment variable not found. Request might fail.")

        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            ocr_options=RapidOcrOptions(),
            do_table_structure=True,
            generate_picture_images=True,
            images_scale=2.0,
            do_picture_description=True,  # Activated to enable VLM tagging
            enable_remote_services=True,
            picture_description_options=PictureDescriptionApiOptions(
                url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                headers={"Authorization": f"Bearer {gemini_api_key}"},
                params={"model": "gemini-2.5-flash-lite"},
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

    @classmethod
    def convert(cls, file_path: str) -> str:
        """Converts a PDF and returns its Markdown representation."""
        converter = cls._get_converter()
        print(f"Starting conversion for: {file_path} (This may take a moment if Gemini is processing figures)...")
        
        result = converter.convert(file_path)
        return result.document.export_to_markdown()


if __name__ == "__main__":
    
    target_file = sys.argv[1] if len(sys.argv) > 1 else "sample.pdf"
    try:
        markdown_output = GeminiDocConverter.convert(target_file)
        
        print("\n--- Conversion Successful! Output Preview ---\n")
        print(markdown_output)
        
    except Exception as e:
        print(f"\nAn error occurred during processing: {e}")