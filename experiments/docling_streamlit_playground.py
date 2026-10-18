import tempfile
from pathlib import Path

import streamlit as st

from docling.datamodel.base_models import InputFormat
# Import RapidOcrOptions instead of EasyOcrOptions
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

st.set_page_config(page_title="Docling", layout="wide")
st.title("File to Markdown (Docling)")

uploaded = st.file_uploader(
    "Upload a document", type=["pdf", "docx", "pptx", "html", "png", "jpg", "jpeg"]
)
run = st.button("Convert", type="primary", disabled=uploaded is None)

if run:
    suffix = Path(uploaded.name).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        input_path = Path(tmp.name)

    try:
        with st.spinner("Converting..."):
            # Pin the OCR engine to RapidOCR (which defaults to stable PP-OCRv4)
            pipeline_options = PdfPipelineOptions(
                do_ocr=True,
                ocr_options=RapidOcrOptions(),
            )
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            doc = converter.convert(input_path).document
            markdown = doc.export_to_markdown()
        st.success(f"Done ({len(markdown)} characters).")
        st.markdown(markdown)
    except Exception as e:
        st.error(f"Conversion failed: {e}")
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except PermissionError:
            pass  # Windows: a library still holds a handle on the temp file
