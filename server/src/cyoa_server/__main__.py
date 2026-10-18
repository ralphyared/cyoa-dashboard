"""Run the dashboard: ``python -m cyoa_server`` (configured by environment variables)."""

from __future__ import annotations

import logging
import os

import uvicorn

from .app import create_app
from .config import Config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = Config.from_env()
    app = create_app(config)
    uvicorn.run(
        app,
        host=os.environ.get("CYOA_HOST", "0.0.0.0"),
        port=int(os.environ.get("CYOA_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
    )


if __name__ == "__main__":
    main()
