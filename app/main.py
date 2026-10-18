"""
FastAPI server - Python port of server.ts
Provides the REST API for the Enterprise LlamaIndex RAG application.
"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.docling import DoclingService
from app.services.presidio import PresidioService
from app.services.rag import RagService

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


def get_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = get_api_key()
    try:
        await RagService.initialize(api_key)
        logger.info("[Server] LlamaIndex RAG Pipeline successfully booted.")
    except Exception as err:
        logger.error("[Server] Critical error during RAG Pipeline boot: %s", err)
    yield


app = FastAPI(title="Enterprise LlamaIndex RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The pure-Docling pipeline saves a cropped PNG for every extracted figure
# to ./figures/<document_id>/<fig_id>.png (see DoclingService._extract_figures
# / FIGURES_OUTPUT_DIR) and only stores that relative path in `imageLink` --
# it never sets `base64Image` for these. Without this mount, the Streamlit
# UI (or any client) has no way to actually fetch and display them.
os.makedirs("figures", exist_ok=True)
app.mount("/figures", StaticFiles(directory="figures"), name="figures")


# ==========================================
# Schemas
# ==========================================
class ChatRequest(BaseModel):
    message: str


class SettingsUpdate(BaseModel):
    chunkSize: int | None = None
    chunkOverlap: int | None = None
    temperature: float | None = None
    topK: int | None = None
    similarityThreshold: float | None = None
    rerankerModel: str | None = None
    activeFilters: dict | None = None


# ==========================================
# API ENDPOINTS
# ==========================================
@app.get("/api/health")
async def health():
    api_key = get_api_key()
    return {
        "status": "healthy",
        "apiKeyConfigured": bool(api_key),
        "llamaindexReady": True,
    }


@app.get("/api/settings")
async def get_settings():
    return RagService.get_settings()


@app.post("/api/settings")
async def update_settings(settings: SettingsUpdate):
    try:
        RagService.update_settings(settings.model_dump(exclude_none=True))
        return {"message": "Settings successfully updated", "settings": RagService.get_settings()}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/api/pii/mappings")
async def get_pii_mappings():
    mappings = PresidioService.get_mappings()
    return {"totalMappings": len(mappings), "mappings": mappings}


@app.delete("/api/pii/clear")
async def clear_pii_mappings():
    PresidioService.clear_mappings()
    return {"message": "Presidio entity mappings successfully cleared."}


@app.get("/api/documents")
async def get_documents():
    return RagService.get_documents()


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured in Secrets.")

    if not file:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    file_bytes = await file.read()
    file_name = file.filename or "unnamed_file"
    mime_type = file.content_type or "application/octet-stream"

    # 15 MB limit (matches multer config in the original TS server)
    if len(file_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds the 15MB upload limit.")

    logger.info("[Server] Received document upload: %s, mime: %s", file_name, mime_type)

    try:
        # 1. Run Docling multi-modal parser to extract hierarchical layouts, tables, and images
        parsed_doc = await DoclingService.parse_document(file_bytes, file_name, mime_type, api_key)

        # 2. Ingest document into LlamaIndex persistent index (with automatic Presidio PII masking)
        await RagService.ingest_document(parsed_doc)

        return {
            "message": "Document successfully parsed and indexed into LlamaIndex",
            "document": {
                "documentId": parsed_doc.documentId,
                "fileName": parsed_doc.fileName,
                "fileType": parsed_doc.fileType,
                "tableCount": len(parsed_doc.tables),
                "figureCount": len(parsed_doc.figures),
                "metadata": parsed_doc.metadata,
            },
        }
    except Exception as error:
        logger.error("[Server] Document parsing failed: %s", error)
        raise HTTPException(
            status_code=500, detail=str(error) or "Failed to parse and index document."
        )


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    try:
        await RagService.delete_document(doc_id)
        return {"message": f"Document {doc_id} deleted successfully."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/api/chat")
async def chat(request: ChatRequest):
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured in Secrets.")

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message content is required.")

    try:
        result = await RagService.run_agentic_workflow(request.message, api_key)
        return {
            "answer": result.answer,
            "maskedAnswer": result.maskedAnswer,
            "citations": [c.__dict__ for c in result.citations],
            "processingTimeMs": result.processingTimeMs,
            "steps": result.steps,
            "guardrailsPassed": result.guardrailsPassed,
            "piiMaskedCount": result.piiMaskedCount,
        }
    except Exception as error:
        logger.error("[Server] Chat processing error: %s", error)
        raise HTTPException(
            status_code=500, detail=str(error) or "An error occurred during chat reasoning."
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=3000, reload=True)