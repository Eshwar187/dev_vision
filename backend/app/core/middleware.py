import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates an X-Request-ID (UUIDv4),
    injects it into the request state, structlog context,
    and returns it in the response headers along with timing info.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract existing X-Request-ID or generate new UUIDv4
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-MS"] = f"{process_time_ms:.2f}"

        return response
