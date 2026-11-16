"""Run the API: `python -m api`. Host and port come from HOST and PORT (defaults 127.0.0.1 and 8000).

On a platform (Railway, Docker) set HOST=0.0.0.0 (or :: for IPv6 too); PORT is usually injected for you.
With DATA_DIR set, the writable folders are first linked into that directory (api/datadir.py).
One process on purpose: running jobs and their progress live in this process's memory.
"""

from __future__ import annotations

import os

import uvicorn

from api import datadir


def main() -> None:
    """Prepare DATA_DIR (when set), then serve api.main:app on HOST:PORT."""
    datadir.prepare()
    host = (os.environ.get("HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("PORT") or "8000").strip())
    # proxy_headers/forwarded_allow_ips: behind Railway's edge the client address and scheme come from
    # X-Forwarded-* headers. Nothing here trusts them for authentication.
    uvicorn.run("api.main:app", host=host, port=port, workers=1, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
