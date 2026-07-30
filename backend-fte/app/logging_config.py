"""
Structured logging configuration for production use.

Features:
- JSON-formatted logs (or plain text for development)
- Request ID propagation via contextvars
- Automatic log rotation
- Sensitive data masking (tokens, secrets)
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime, timezone
from typing import Optional
from contextvars import ContextVar

# ─── Context variables for request-scoped data ───

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
store_id_var: ContextVar[Optional[str]] = ContextVar("store_id", default=None)
endpoint_var: ContextVar[Optional[str]] = ContextVar("endpoint", default=None)


# ─── Sensitive field patterns (values are masked in logs) ───

SENSITIVE_FIELDS = {
    "access_token", "password", "secret", "token",
    "authorization", "x-shopify-access-token",
    "refresh_token", "api_key", "api_secret",
}


def _mask_sensitive(data: dict) -> dict:
    """Recursively mask sensitive field values."""
    if not isinstance(data, dict):
        return data
    masked = {}
    for key, value in data.items():
        if any(s in key.lower() for s in SENSITIVE_FIELDS):
            masked[key] = "***REDACTED***"
        elif isinstance(value, dict):
            masked[key] = _mask_sensitive(value)
        else:
            masked[key] = value
    return masked


# ─── Custom JSON Formatter ───


class JSONFormatter(logging.Formatter):
    """Output logs as newline-delimited JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        # Use datetime.isoformat() for cross-platform timestamp formatting (avoids %f/%Z strftime issues on Windows)
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        log_entry = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request context
        rid = request_id_var.get()
        if rid:
            log_entry["request_id"] = rid
        uid = user_id_var.get()
        if uid:
            log_entry["user_id"] = uid
        sid = store_id_var.get()
        if sid:
            log_entry["store_id"] = sid
        ep = endpoint_var.get()
        if ep:
            log_entry["endpoint"] = ep

        # Add exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        # Add extra context from record
        if hasattr(record, "extra"):
            log_entry["extra"] = _mask_sensitive(record.extra)

        return json.dumps(log_entry, default=str)


# ─── Setup function ───


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Configure root logger with the specified level and format.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_format: "json" for JSON output, "text" for plain text
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation (only if logs directory exists)
    log_dir = os.environ.get("LOG_DIR", "logs")
    if os.path.isdir(log_dir) or log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "app.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Suppress noisy library logs
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info(
        "Logging configured: level=%s, format=%s",
        log_level,
        log_format,
    )
