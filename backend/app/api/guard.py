"""Keep the localhost API local: writes only from the app's own origin, and bounded bodies.

The Host check (DNS rebinding) is Starlette's TrustedHostMiddleware, added in app/main.py.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 2_000_000
# The Vite dev server proxies /api, so browser writes carry its origin. Non-browser clients
# (curl, tests, Playwright's request API) send no Origin header at all.
ALLOWED_ORIGINS = frozenset({"http://127.0.0.1:5173", "http://localhost:5173"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": {"message": message}}, status_code=status)


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        origin = headers.get("origin")
        if (
            scope["method"] in UNSAFE_METHODS
            and origin is not None
            and origin not in ALLOWED_ORIGINS
        ):
            await _error(403, "cross-origin write refused")(scope, receive, send)
            return
        length = headers.get("content-length")
        if length is not None and not (
            length.isascii() and length.isdigit() and int(length) <= MAX_BODY_BYTES
        ):
            await _error(413, "request body too large")(scope, receive, send)
            return

        # Chunked bodies have no Content-Length: count bytes as they arrive.
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not too_large:  # drop whatever the app answers to the cut-off request
                await send(message)

        await self.app(scope, limited_receive, guarded_send)
        if too_large:
            await _error(413, "request body too large")(scope, receive, send)
