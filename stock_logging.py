from __future__ import annotations

import logging
from pathlib import Path

from stock_constants import ENCODING, LOG_DIR, LOG_FILE


def setup_stock_logging(log_dir: str | Path = LOG_DIR) -> Path:
    log_path = Path(log_dir) / LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("domain_layer")
    logger.setLevel(logging.INFO)

    resolved_log_path = log_path.resolve()
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == resolved_log_path:
            return log_path

    handler = logging.FileHandler(log_path, encoding=ENCODING)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return log_path
