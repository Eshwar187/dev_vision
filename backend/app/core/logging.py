import logging
import sys
from typing import Any, Dict, MutableMapping
import structlog
from app.core.config import get_settings

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "session_token",
    "csrf_token",
    "authorization",
    "api_key",
    "cookie",
    "cookies",
    "file_bytes",
    "prompt",
    "raw_prompt",
    "text_content",
    "embedding",
    "embeddings",
}


def sanitize_sensitive_data(
    logger: logging.Logger, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Sanitizes credentials, raw prompts, document text, and embeddings from structured logs."""
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if key_lower in SENSITIVE_KEYS or any(s in key_lower for s in ("password", "secret", "token", "auth")):
            if key not in ("request_id", "fencing_token"):  # Allow opaque tracking identifiers
                event_dict[key] = "[REDACTED]"
        elif key in ("document_content", "passage", "passages", "excerpt"):
            # Never log full document bodies or context passages
            val = event_dict[key]
            if isinstance(val, str) and len(val) > 100:
                event_dict[key] = f"[TRUNCATED {len(val)} chars]"
    return event_dict


def setup_logging() -> None:
    """Configures structured JSON / console logging for DevVision AI."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        sanitize_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT.lower() == "json":
        formatter_processor = structlog.processors.JSONRenderer()
    else:
        formatter_processor = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            formatter_processor,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for logger_name in ("uvicorn.access", "botocore", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str = "devvision"):
    """Returns a structured logger instance."""
    return structlog.get_logger(name)
