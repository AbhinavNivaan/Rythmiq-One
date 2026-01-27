"""
Correlation ID middleware.
Owns: Request tracing via correlation IDs.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationMiddleware(BaseHTTPMiddleware):
    HEADER_NAME = "X-Correlation-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = request.headers.get(self.HEADER_NAME)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[self.HEADER_NAME] = correlation_id

        return response
