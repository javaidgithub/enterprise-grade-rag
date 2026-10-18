# #!/usr/bin/env python3
# """
# run.py  –  Start the Enterprise LlamaIndex RAG stack.

# Usage:
#     python run.py              # starts both FastAPI backend + Streamlit frontend
#     python run.py --api-only   # starts only the FastAPI backend
#     python run.py --ui-only    # starts only the Streamlit frontend
# """
# import argparse
# import subprocess
# import sys
# import os
# import threading
# import signal
# import time


# def start_api():
#     print("[run.py] Starting FastAPI backend on http://0.0.0.0:3000 ...")
#     subprocess.run(
#         [
#             sys.executable, "-m", "uvicorn",
#             "app.main:app",
#             "--host", "0.0.0.0",
#             "--port", "3000",
#             "--reload",
#             # `figures/` (extracted figure PNGs) and `storage/` (LlamaIndex
#             # persistence) are written by the app itself at runtime. Without
#             # excluding them, --reload's file watcher treats every saved
#             # figure or persisted index as a "code change" and restarts the
#             # server mid-request, which can leave nothing listening on the
#             # port (seen as "connection actively refused").
#             "--reload-exclude", "figures/*",
#             "--reload-exclude", "storage/*",
#         ],
#         check=True,
#     )


# def start_ui():
#     print("[run.py] Starting Streamlit frontend on http://0.0.0.0:8501 ...")
#     subprocess.run(
#         [
#             sys.executable, "-m", "streamlit", "run",
#             "streamlit_app.py",
#             "--server.address", "0.0.0.0",
#             "--server.port", "8501",
#         ],
#         check=True,
#     )


# def main():
#     parser = argparse.ArgumentParser(description="Enterprise LlamaIndex RAG launcher")
#     parser.add_argument("--api-only", action="store_true", help="Only run the FastAPI backend")
#     parser.add_argument("--ui-only", action="store_true", help="Only run the Streamlit UI")
#     args = parser.parse_args()

#     if args.api_only:
#         start_api()
#     elif args.ui_only:
#         start_ui()
#     else:
#         # Run both concurrently in threads; kill both on Ctrl-C
#         api_thread = threading.Thread(target=start_api, daemon=True)
#         api_thread.start()

#         # Give the API a moment to boot before the UI opens
#         time.sleep(2)

#         try:
#             start_ui()  # blocks until Streamlit exits
#         except KeyboardInterrupt:
#             print("\n[run.py] Shutting down.")
#             sys.exit(0)


# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
"""
run.py  –  Start the Enterprise LlamaIndex RAG stack.

Usage:
    python run.py              # starts both FastAPI backend + Streamlit frontend
    python run.py --api-only   # starts only the FastAPI backend
    python run.py --ui-only    # starts only the Streamlit frontend
"""
import argparse
import subprocess
import sys
import os
import threading
import signal
import time


def start_api():
    print("[run.py] Starting FastAPI backend on http://0.0.0.0:3000 ...")
    subprocess.run(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", "3000",
            "--reload",
            # Scope the reloader to the source directory instead of trying
            # to exclude `figures/*` and `storage/*` with glob patterns.
            # On Windows, a bare wildcard token like "storage/*" can get
            # expanded into literal filenames before uvicorn's CLI parser
            # (click) ever sees it -- which crashes with "Got unexpected
            # extra arguments" the moment storage/ has files in it.
            # --reload-dir sidesteps that entirely: only files under app/
            # are watched, so runtime writes to figures/ and storage/
            # never trigger a reload in the first place.
            "--reload-dir", "app",
        ],
        check=True,
    )


def start_ui():
    print("[run.py] Starting Streamlit frontend on http://0.0.0.0:8501 ...")
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            "streamlit_app.py",
            "--server.address", "0.0.0.0",
            "--server.port", "8501",
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Enterprise LlamaIndex RAG launcher")
    parser.add_argument("--api-only", action="store_true", help="Only run the FastAPI backend")
    parser.add_argument("--ui-only", action="store_true", help="Only run the Streamlit UI")
    args = parser.parse_args()

    if args.api_only:
        start_api()
    elif args.ui_only:
        start_ui()
    else:
        # Run both concurrently in threads; kill both on Ctrl-C
        api_thread = threading.Thread(target=start_api, daemon=True)
        api_thread.start()

        # Give the API a moment to boot before the UI opens
        time.sleep(2)

        try:
            start_ui()  # blocks until Streamlit exits
        except KeyboardInterrupt:
            print("\n[run.py] Shutting down.")
            sys.exit(0)


if __name__ == "__main__":
    main()