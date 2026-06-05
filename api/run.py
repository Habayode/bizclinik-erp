"""Convenience launcher for the BizClinik ERP REST API.

The API is a SEPARATE service from the Streamlit UI and listens on port 8600.

Run it directly:

    python -m api.run

or, equivalently, via uvicorn:

    python -m uvicorn api.main:app --host 127.0.0.1 --port 8600

Environment:
    BIZCLINIK_API_KEY       required — clients must send it as X-API-Key.
    BIZCLINIK_WEBHOOK_URLS  optional — comma-separated webhook endpoints.
    BIZCLINIK_DB_PATH       optional — sqlite file (shared with the Streamlit app).
"""
from __future__ import annotations

HOST = "127.0.0.1"
PORT = 8600


def main() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
