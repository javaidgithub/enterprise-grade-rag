"""
Streamlit frontend – complete Python port of the React UI.

Mirrors every feature of:
  - App.tsx          (shell, sidebar, health badge, tab routing)
  - ChatInterface.tsx (messages, masked/unmasked toggle, colour-coded trace logs,
                       citation cards with score + quote, quick-prompt chips)
  - DocumentManager.tsx (drag-and-drop uploader, document list with badges,
                         tabbed inspector: Structured Markdown / Tables / Figures / Raw Text)
  - SettingsPanel.tsx   (all sliders, reranker select, PII mapping audit table)

Run order:
    uvicorn app.main:app --port 3000      # (or: python run.py --api-only)
    streamlit run streamlit_app.py
"""
import os
import time
import uuid
import io

import requests
import streamlit as st

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
API_BASE = os.environ.get("RAG_API_BASE", "http://localhost:3000")

st.set_page_config(
    page_title="Enterprise LlamaIndex RAG",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ---- general resets ---- */
    .block-container { padding-top: 1.5rem; }

    /* ---- sidebar brand ---- */
    .rag-brand  { font-size: 1.25rem; font-weight: 800; color: #4f46e5; }
    .rag-sub    { font-size: 0.7rem;  color: #6b7280;  margin-top: -4px; }

    /* ---- status pill ---- */
    .pill-ok  { background:#d1fae5; color:#065f46; border-radius:999px; padding:2px 10px; font-size:.72rem; font-weight:600; }
    .pill-warn{ background:#fef3c7; color:#92400e; border-radius:999px; padding:2px 10px; font-size:.72rem; font-weight:600; }
    .pill-err { background:#fee2e2; color:#991b1b; border-radius:999px; padding:2px 10px; font-size:.72rem; font-weight:600; }

    /* ---- chat bubbles ---- */
    .bubble-user {
        background: #4f46e5; color: #fff;
        padding: .65rem 1rem; border-radius: 1rem 1rem 0 1rem;
        font-size: .83rem; line-height: 1.5;
        display: inline-block; max-width: 85%;
    }
    .bubble-bot {
        background: #f9fafb; color: #1f2937;
        border: 1px solid #e5e7eb;
        padding: .65rem 1rem; border-radius: 1rem 1rem 1rem 0;
        font-size: .83rem; line-height: 1.5;
        display: inline-block; max-width: 85%;
        white-space: pre-wrap;
    }
    .bubble-meta { font-size:.68rem; color:#9ca3af; margin-top:3px; font-family:monospace; }

    /* ---- trace log block ---- */
    .trace-block {
        background: #111827; border-radius: .6rem;
        padding: .75rem 1rem; font-family: monospace;
        font-size: .72rem; line-height: 1.6;
        overflow-x: auto;
    }
    .trace-default  { color: #d1d5db; }
    .trace-pii      { color: #fbbf24; font-weight: 700; }
    .trace-blocked  { color: #f87171; font-weight: 700; }
    .trace-success  { color: #34d399; }
    .trace-decision { color: #60a5fa; font-weight: 700; }
    .trace-rerank   { color: #a5b4fc; }
    .trace-index    { color: #6b7280; }

    /* ---- citation card ---- */
    .cite-card {
        border: 1px solid #e5e7eb; border-radius: .75rem;
        padding: .65rem .9rem; background: #fff;
        font-size: .78rem; margin-bottom: .4rem;
    }
    .cite-badge  { background:#ede9fe; color:#4f46e5; border-radius:.3rem;
                   padding:1px 7px; font-size:.68rem; font-weight:700; }
    .cite-score  { font-family:monospace; color:#9ca3af; font-size:.68rem; }
    .cite-fname  { font-weight:600; color:#1f2937; }
    .cite-quote  { color:#6b7280; font-size:.7rem; font-style:italic;
                   overflow:hidden; display:-webkit-box;
                   -webkit-line-clamp:2; -webkit-box-orient:vertical; }

    /* ---- table viewer ---- */
    .tbl-wrap { overflow-x:auto; }
    .tbl-wrap table { border-collapse:collapse; font-size:.76rem; width:100%; }
    .tbl-wrap th { background:#f3f4f6; padding:6px 10px; text-align:left;
                   font-weight:700; border-bottom:2px solid #e5e7eb; }
    .tbl-wrap td { padding:5px 10px; border-bottom:1px solid #f3f4f6; color:#374151; }
    .tbl-wrap tr:hover td { background:#f9fafb; }

    /* ---- figure card ---- */
    .fig-card { border:1px solid #e5e7eb; border-radius:.75rem;
                padding:1rem; background:#f9fafb; margin-bottom:.75rem; }
    .fig-title { font-weight:700; font-size:.8rem; color:#1f2937; }
    .fig-desc  { font-size:.75rem; color:#4b5563; margin-top:.4rem;
                 line-height:1.5; }

    /* ---- upload zone ---- */
    .upload-hint { text-align:center; color:#9ca3af;
                   font-size:.72rem; margin-top:.35rem; }

    /* ---- doc row ---- */
    .doc-row { display:flex; align-items:center; justify-content:space-between;
               border:1px solid #e5e7eb; border-radius:.65rem; padding:.5rem .75rem;
               background:#fff; margin-bottom:.4rem; cursor:pointer; }
    .doc-row:hover { border-color:#a5b4fc; background:#f5f3ff; }
    .doc-row.active { border-color:#4f46e5; background:#ede9fe33; }
    .doc-badge { font-size:.62rem; font-weight:700; text-transform:uppercase;
                 background:#f3f4f6; color:#6b7280; border-radius:.25rem;
                 padding:1px 5px; }

    /* ---- section header ---- */
    .sec-hdr { font-size:.85rem; font-weight:700; color:#111827; margin-bottom:.5rem; }

    /* ---- empty state ---- */
    .empty-state { text-align:center; padding:2.5rem 1rem;
                   border:1px dashed #e5e7eb; border-radius:.75rem;
                   color:#9ca3af; }
    .empty-state p { font-size:.8rem; margin-top:.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------
# Session state
# ---------------------------------------------------------------
for key, default in {
    "messages": [],
    "settings": {
        "chunkSize": 512,
        "chunkOverlap": 50,
        "temperature": 0.1,
        "topK": 4,
        "similarityThreshold": 0.3,
        "rerankerModel": "llm",
    },
    "selected_doc_id": None,
    "inspector_tab": "markdown",
    "show_masked": {},   # msg_id -> bool
    "show_trace": {},    # msg_id -> bool
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------
def _api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{API_BASE}{path}", timeout=180, **kwargs)
        r.raise_for_status()
        return r.json(), None
    except requests.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        return None, detail
    except Exception as e:
        return None, str(e)


def api_get(path):
    data, err = _api("get", path)
    return data, err


def api_post(path, json_body=None):
    data, err = _api("post", path, json=json_body)
    return data, err


def api_delete(path):
    data, err = _api("delete", path)
    return data, err


def api_upload(file_obj):
    try:
        files = {"file": (file_obj.name, file_obj.getvalue(), file_obj.type)}
        r = requests.post(f"{API_BASE}/api/documents/upload", files=files, timeout=300)
        r.raise_for_status()
        return r.json(), None
    except requests.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        return None, detail
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------
# Health + Sidebar
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="rag-brand">🤖 Enterprise RAG</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="rag-sub">LlamaIndex · Docling · Presidio · Gemini</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    health, h_err = api_get("/api/health")
    if h_err:
        st.markdown('<span class="pill-err">⚠ Backend unreachable</span>', unsafe_allow_html=True)
    elif not health.get("apiKeyConfigured"):
        st.markdown(
            '<span class="pill-warn">⚠ GEMINI_API_KEY not set</span>', unsafe_allow_html=True
        )
        st.caption("Set GEMINI_API_KEY in your .env file.")
    else:
        st.markdown('<span class="pill-ok">🔐 API key configured</span>', unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    page = st.radio(
        "Navigate",
        ["💬  Chat", "📄  Documents", "⚙️  Settings"],
        label_visibility="collapsed",
    )


# ================================================================
#  HELPERS
# ================================================================

def render_trace_log(steps: list[str], msg_id: str, latency_ms: float):
    """Collapsible dark terminal log, colour-coded like the TS UI."""
    key = f"trace_{msg_id}"
    if key not in st.session_state.show_trace:
        st.session_state.show_trace[key] = False

    label = (
        "▾ Hide agent trace"
        if st.session_state.show_trace[key]
        else "▸ Show agent trace & guardrail logs"
    )
    if st.button(label, key=f"btn_trace_{msg_id}", use_container_width=False):
        st.session_state.show_trace[key] = not st.session_state.show_trace[key]
        st.rerun()

    if st.session_state.show_trace[key]:
        lines_html = ""
        for i, step in enumerate(steps):
            if "Detected PII" in step or "Masked" in step:
                css = "trace-pii"
            elif "Violation" in step or "Blocked" in step or "halted" in step:
                css = "trace-blocked"
            elif "Success" in step or "cleared" in step or "Grounding Validation Success" in step:
                css = "trace-success"
            elif "Decision" in step:
                css = "trace-decision"
            elif "Rerank" in step or "rerank" in step:
                css = "trace-rerank"
            else:
                css = "trace-default"
            step_safe = step.replace("<", "&lt;").replace(">", "&gt;")
            lines_html += f'<div><span class="trace-index">[{i+1}]</span> <span class="{css}">{step_safe}</span></div>'

        st.markdown(
            f'<div class="trace-block">{lines_html}'
            f'<div class="trace-index" style="margin-top:.5rem">Latency: {latency_ms:.0f} ms</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_citation_cards(citations: list[dict]):
    """Grid of citation cards (2 columns)."""
    cols = st.columns(2)
    for i, c in enumerate(citations):
        score = c.get("score", 0)
        fname = c.get("fileName", "Unknown")
        quote = c.get("text", "")[:300]
        content_type = c.get("contentType", "text")
        type_icon = {"table": "📊", "figure": "🖼", "structured_markdown": "📄"}.get(
            content_type, "📄"
        )
        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="cite-card">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                    <span class="cite-badge">Source {i+1} · {type_icon} {content_type}</span>
                    <span class="cite-score">Score: {score:.2f}</span>
                  </div>
                  <div class="cite-fname">📄 {fname}</div>
                  <div class="cite-quote">"{quote}"</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Figure citations carry a real image crop now (pure-Docling
            # populates imageLink for every figure) -- show it inline.
            if content_type == "figure" and c.get("imageLink"):
                img_url = f"{API_BASE}/{c['imageLink'].lstrip('/')}"
                st.image(img_url, use_container_width=False, width=280)


def markdown_table_to_html(md: str) -> str:
    """Convert a markdown table string to an HTML table."""
    lines = [l.strip() for l in md.strip().splitlines() if l.strip()]
    rows = [l for l in lines if l.startswith("|")]
    if not rows:
        return f"<pre>{md}</pre>"

    def cells(row):
        parts = row.split("|")
        return [p.strip() for p in parts[1:-1]]

    headers = cells(rows[0])
    data_rows = [cells(r) for r in rows[2:]]  # skip separator row

    th = "".join(f"<th>{h}</th>" for h in headers)
    tbody = ""
    for row in data_rows:
        td = "".join(f"<td>{c}</td>" for c in row)
        tbody += f"<tr>{td}</tr>"

    return (
        f'<div class="tbl-wrap"><table>'
        f"<thead><tr>{th}</tr></thead>"
        f"<tbody>{tbody}</tbody>"
        f"</table></div>"
    )


# ================================================================
#  💬  CHAT  (ChatInterface.tsx)
# ================================================================
if page == "💬  Chat":
    st.markdown('<div class="sec-hdr">LlamaIndex Agentic Chat</div>', unsafe_allow_html=True)
    st.caption(
        "Powered by Presidio PII redaction · Docling layout ingestion · LLM reranker · hallucination guardrails"
    )

    docs, _ = api_get("/api/documents")
    has_docs = bool(docs)

    # ---- Empty-state quick-prompt chips ----
    if not st.session_state.messages:
        st.markdown("<br/>", unsafe_allow_html=True)
        st.markdown(
            '<div class="empty-state">'
            "<b>Conversational RAG Agent</b>"
            + (
                "<p>Ask anything about your uploaded knowledge documents.<br/>"
                "The agent will automatically decide when to search the vector store.</p>"
                if has_docs
                else "<p>Upload a document in the Documents tab, then ask a question<br/>"
                "to test PII masking, retrieval, and citation synthesis.</p>"
            )
            + "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<br/>", unsafe_allow_html=True)
        c1, c2, _ = st.columns([1, 1, 2])
        with c1:
            if st.button("🔍 Topic summary?", use_container_width=True):
                st.session_state["_quick_prompt"] = "What is the main topic of my uploaded document?"
        with c2:
            if st.button("📊 Extract tabular data?", use_container_width=True):
                st.session_state["_quick_prompt"] = (
                    "Can you list all structured tables extracted from my files?"
                )

    # ---- Message history ----
    for msg in st.session_state.messages:
        mid = msg["id"]
        is_user = msg["sender"] == "user"

        if is_user:
            cols = st.columns([1, 3])
            with cols[1]:
                st.markdown(
                    f'<div style="text-align:right">'
                    f'<span style="font-size:.68rem;color:#9ca3af;font-family:monospace">User 👤</span>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:flex-end">'
                    f'<div class="bubble-user">{msg["text"]}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            has_masked = bool(msg.get("maskedText") and msg["maskedText"] != msg["text"])
            show_masked = st.session_state.show_masked.get(mid, False)
            displayed_text = msg.get("maskedText", msg["text"]) if show_masked else msg["text"]

            st.markdown(
                '<span style="font-size:.68rem;color:#6b7280;font-family:monospace">🤖 LlamaIndex RAG Agent</span>',
                unsafe_allow_html=True,
            )

            # Masked / de-masked toggle
            if has_masked:
                toggle_label = (
                    "👁 View de-masked (original)" if show_masked else "🔒 View masked payload"
                )
                if st.button(toggle_label, key=f"masked_toggle_{mid}"):
                    st.session_state.show_masked[mid] = not show_masked
                    st.rerun()

            st.markdown(
                f'<div class="bubble-bot">{displayed_text}</div>',
                unsafe_allow_html=True,
            )

            if not msg.get("guardrailsPassed", True):
                st.warning("⚠️ Security guardrail blocked this response.", icon="🛡")

            # Trace logs
            if msg.get("steps"):
                render_trace_log(msg["steps"], mid, msg.get("processingTimeMs", 0))

            # Citations
            if msg.get("citations"):
                with st.expander(f"📎 Citations ({len(msg['citations'])})"):
                    render_citation_cards(msg["citations"])

    # ---- Input ----
    quick = st.session_state.pop("_quick_prompt", None)
    placeholder = (
        "Ask your agent a question..."
        if has_docs
        else "Upload a document first to query custom indexes..."
    )

    prompt = st.chat_input(placeholder)
    if quick:
        prompt = quick

    if prompt:
        msg_id = str(uuid.uuid4())
        st.session_state.messages.append({"id": msg_id, "sender": "user", "text": prompt})

        with st.spinner("Running agentic RAG workflow — scanning PII, routing, retrieving, reranking..."):
            result, err = api_post("/api/chat", {"message": prompt})

        bot_id = str(uuid.uuid4())
        if err or result is None:
            error_text = err or "Unknown error"
            st.error(f"Chat error: {error_text}")
            st.session_state.messages.append(
                {"id": bot_id, "sender": "bot", "text": f"Error: {error_text}"}
            )
        else:
            st.session_state.messages.append(
                {
                    "id": bot_id,
                    "sender": "bot",
                    "text": result.get("answer", ""),
                    "maskedText": result.get("maskedAnswer"),
                    "steps": result.get("steps", []),
                    "citations": result.get("citations", []),
                    "processingTimeMs": result.get("processingTimeMs", 0),
                    "guardrailsPassed": result.get("guardrailsPassed", True),
                }
            )
        st.rerun()


# ================================================================
#  📄  DOCUMENTS  (DocumentManager.tsx)
# ================================================================
elif page == "📄  Documents":
    left, right = st.columns([5, 7], gap="large")

    with left:
        # ---- Upload Zone ----
        st.markdown('<div class="sec-hdr">Ingest Document</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Drag & drop or click to upload",
            type=["pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "html",
                  "png", "jpg", "jpeg", "gif", "webp"],
            label_visibility="collapsed",
        )
        st.markdown(
            '<div class="upload-hint">PDF · DOCX · PPTX · XLSX · CSV · PNG · JPG · MD · TXT (max 15 MB)</div>',
            unsafe_allow_html=True,
        )

        if uploaded is not None:
            if st.button("⚡ Parse & Ingest", type="primary", use_container_width=True):
                with st.spinner(
                    f"Parsing {uploaded.name} with Docling · ingesting into LlamaIndex..."
                ):
                    result, err = api_upload(uploaded)
                if err:
                    st.error(f"Ingestion failed: {err}")
                else:
                    doc = result["document"]
                    st.success(
                        f"✅ **{doc['fileName']}** ingested "
                        f"({doc['tableCount']} tables · {doc['figureCount']} figures)"
                    )
                    time.sleep(0.4)
                    st.rerun()

        st.markdown("---")

        # ---- Document List ----
        documents, _ = api_get("/api/documents")
        documents = documents or []

        st.markdown(
            f'<div class="sec-hdr">Knowledge Base Index'
            f'<span style="float:right;font-size:.7rem;background:#f3f4f6;'
            f'color:#6b7280;border-radius:999px;padding:1px 9px;font-weight:700">'
            f'{len(documents)} docs</span></div>',
            unsafe_allow_html=True,
        )

        if not documents:
            st.markdown(
                '<div class="empty-state">📂<p>Knowledge base empty.<br/>'
                "Upload a document to build your enterprise semantic retriever.</p></div>",
                unsafe_allow_html=True,
            )
        else:
            for doc in documents:
                did = doc["documentId"]
                is_selected = st.session_state.selected_doc_id == did
                row_class = "doc-row active" if is_selected else "doc-row"

                col_info, col_del = st.columns([8, 1])
                with col_info:
                    clicked = st.button(
                        f"📄  **{doc['fileName']}**  "
                        f"`{doc['fileType']}`  ·  "
                        f"{len(doc.get('tables',[]))} tables · {len(doc.get('figures',[]))} figs",
                        key=f"sel_{did}",
                        use_container_width=True,
                    )
                    if clicked:
                        st.session_state.selected_doc_id = did
                        st.session_state.inspector_tab = "markdown"
                        st.rerun()
                with col_del:
                    if st.button("🗑", key=f"del_{did}", help="Delete document"):
                        _, err = api_delete(f"/api/documents/{did}")
                        if err:
                            st.error(err)
                        else:
                            if st.session_state.selected_doc_id == did:
                                st.session_state.selected_doc_id = None
                            st.rerun()

    # ---- Document Inspector (right column) ----
    with right:
        sel_id = st.session_state.selected_doc_id
        sel_doc = None
        if sel_id and documents:
            sel_doc = next((d for d in documents if d["documentId"] == sel_id), None)

        if sel_doc is None:
            st.markdown("<br/><br/>", unsafe_allow_html=True)
            st.markdown(
                '<div class="empty-state">📖'
                "<b>Docling Structured Document Inspector</b>"
                "<p>Select any document from the list to inspect its layout structure,<br/>"
                "parsed tables, and extracted figures.</p></div>",
                unsafe_allow_html=True,
            )
        else:
            file_size = sel_doc.get("metadata", {}).get("fileSize", "n/a")
            page_count = sel_doc.get("metadata", {}).get("pageCount", "n/a")

            st.markdown(
                f'<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:.75rem;padding:.6rem 1rem;margin-bottom:.75rem">'
                f'<span style="font-size:.65rem;font-weight:700;color:#4f46e5;text-transform:uppercase;letter-spacing:.05em">Docling Layout Parser</span><br/>'
                f'<span style="font-size:.88rem;font-weight:700;color:#111827">{sel_doc["fileName"]}</span>'
                f'<span style="float:right;font-size:.7rem;color:#9ca3af;font-family:monospace">{file_size} · {page_count} pages</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

            tabs = st.tabs(
                [
                    "📖 Structured Markdown",
                    f"📊 Tables ({len(sel_doc.get('tables', []))})",
                    f"🖼 Figures ({len(sel_doc.get('figures', []))})",
                    "⌨️ Raw Text",
                ]
            )

            # ---- Markdown tab ----
            with tabs[0]:
                md_content = sel_doc.get("structuredMarkdown", "No structured markdown extracted.")
                st.markdown(
                    f'<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:.6rem;'
                    f'padding:1rem;font-size:.8rem;line-height:1.6;white-space:pre-wrap;'
                    f'max-height:460px;overflow-y:auto;font-family:inherit">{md_content}</div>',
                    unsafe_allow_html=True,
                )

            # ---- Tables tab ----
            with tabs[1]:
                tables = sel_doc.get("tables", [])
                if not tables:
                    st.markdown(
                        '<div class="empty-state">📊<p>No tables detected in document structure.</p></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    for i, tbl in enumerate(tables):
                        st.markdown(
                            f'<div style="font-size:.8rem;font-weight:700;color:#111827;margin:.5rem 0 .35rem">'
                            f'<span style="background:#ede9fe;color:#4f46e5;border-radius:.3rem;'
                            f'padding:1px 7px;font-size:.68rem">Table {i+1}</span>  {tbl.get("title","Untitled")}'
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        html_table = markdown_table_to_html(tbl.get("markdown", ""))
                        st.markdown(html_table, unsafe_allow_html=True)
                        st.caption(
                            f"{tbl.get('rowCount', '?')} rows · {tbl.get('colCount', '?')} columns"
                        )
                        st.markdown("<br/>", unsafe_allow_html=True)

            # ---- Figures tab ----
            with tabs[2]:
                figures = sel_doc.get("figures", [])
                if not figures:
                    st.markdown(
                        '<div class="empty-state">🖼<p>No images or figures extracted.</p></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    for i, fig in enumerate(figures):
                        st.markdown(
                            f'<div class="fig-card">'
                            f'<div class="fig-title">Figure {i+1}: {fig.get("title","Untitled")}</div>',
                            unsafe_allow_html=True,
                        )
                        if fig.get("base64Image"):
                            # Streamlit can render data URIs as images
                            b64_src = fig["base64Image"]
                            st.image(b64_src, use_container_width=False, width=380)
                        elif fig.get("imageLink"):
                            # Pure-Docling figures never set base64Image -- they
                            # store a relative path (e.g. "figures/<doc_id>/fig_0.png")
                            # that the FastAPI backend serves as a static file.
                            img_url = f"{API_BASE}/{fig['imageLink'].lstrip('/')}"
                            st.image(img_url, use_container_width=False, width=380)
                        page_no = fig.get("page")
                        if page_no:
                            st.caption(f"Page {page_no}")
                        st.markdown(
                            f'<div class="fig-desc">'
                            f'<span style="font-size:.65rem;font-weight:700;color:#4f46e5;text-transform:uppercase">Docling Figure Caption / Insights</span><br/>'
                            f'{fig.get("description","")}</div></div>',
                            unsafe_allow_html=True,
                        )

            # ---- Raw Text tab ----
            with tabs[3]:
                raw = sel_doc.get("rawText", "No raw text extracted.")
                st.markdown(
                    f'<pre style="background:#111827;color:#d1d5db;border-radius:.6rem;'
                    f'padding:1rem;font-size:.75rem;line-height:1.6;'
                    f'overflow-y:auto;max-height:460px;white-space:pre-wrap">{raw}</pre>',
                    unsafe_allow_html=True,
                )


# ================================================================
#  ⚙️  SETTINGS  (SettingsPanel.tsx)
# ================================================================
elif page == "⚙️  Settings":
    st.markdown('<div class="sec-hdr">LlamaIndex Pipeline Settings</div>', unsafe_allow_html=True)

    # Sync settings from server
    server_settings, _ = api_get("/api/settings")
    if server_settings:
        for k, v in server_settings.items():
            if k in st.session_state.settings:
                st.session_state.settings[k] = v

    s = st.session_state.settings

    with st.form("settings_form"):
        st.caption("Changes are applied to both the vector pipeline and the Gemini LLM call.")

        chunk_size = st.slider(
            "Chunk Size (chars) — maximum characters per text chunk during ingestion",
            128, 2048, int(s["chunkSize"]), step=64,
        )
        chunk_overlap = st.slider(
            "Chunk Overlap (chars) — overlapping characters between consecutive chunks",
            0, 500, int(s["chunkOverlap"]), step=10,
        )
        temperature = st.slider(
            "LLM Temperature — controls randomness in synthesis and routing calls",
            0.0, 1.0, float(s["temperature"]), step=0.05,
        )
        top_k = st.slider(
            "Top K Retrieved Chunks — candidate nodes to fetch before reranking",
            1, 10, int(s["topK"]), step=1,
        )
        similarity_threshold = st.slider(
            "Similarity Threshold — minimum score to include a retrieved chunk",
            0.0, 1.0, float(s["similarityThreshold"]), step=0.05,
        )
        reranker = st.selectbox(
            "Reranker Model",
            ["llm", "none"],
            index=0 if s.get("rerankerModel", "llm") == "llm" else 1,
            help='"llm" uses Gemini to re-score and reorder retrieved chunks; "none" skips reranking.',
        )

        saved = st.form_submit_button("💾 Save Settings", type="primary")
        if saved:
            new_settings = {
                "chunkSize": chunk_size,
                "chunkOverlap": chunk_overlap,
                "temperature": temperature,
                "topK": top_k,
                "similarityThreshold": similarity_threshold,
                "rerankerModel": reranker,
            }
            result, err = api_post("/api/settings", new_settings)
            if err:
                st.error(f"Failed to update settings: {err}")
            else:
                st.session_state.settings = new_settings
                st.success("✅ Settings successfully updated.")

    st.markdown("---")

    # ---- PII Mapping Audit Panel ----
    st.markdown('<div class="sec-hdr">🔒 Presidio PII Mapping Audit</div>', unsafe_allow_html=True)
    st.caption(
        "Bi-directional mapping store used to mask entities before embedding "
        "and restore them in the final answer."
    )

    pii_data, _ = api_get("/api/pii/mappings")
    pii_data = pii_data or {"totalMappings": 0, "mappings": []}

    col_count, col_btn = st.columns([3, 1])
    with col_count:
        st.metric("Entities currently masked", pii_data["totalMappings"])
    with col_btn:
        st.markdown("<br/>", unsafe_allow_html=True)
        if st.button("🗑 Clear All Mappings", type="secondary"):
            api_delete("/api/pii/clear")
            st.success("Presidio entity mappings cleared.")
            st.rerun()

    mappings = pii_data.get("mappings", [])
    if mappings:
        st.dataframe(
            mappings,
            use_container_width=True,
            hide_index=True,
            column_config={
                "original": st.column_config.TextColumn("Original Value"),
                "masked": st.column_config.TextColumn("Masked Placeholder"),
                "type": st.column_config.TextColumn("Entity Type"),
            },
        )
    else:
        st.markdown(
            '<div class="empty-state">🔐<p>No PII entities have been masked yet.<br/>'
            "Upload a document or send a chat message to populate the mapping store.</p></div>",
            unsafe_allow_html=True,
        )