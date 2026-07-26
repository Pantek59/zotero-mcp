import logging

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from zotero_mcp import mcp
from zotero_mcp.rate_limiter import RateLimitMiddleware

logger = logging.getLogger(__name__)


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"}, status_code=200)


def create_app() -> Starlette:
    mcp_app = mcp.streamable_http_app()

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        middleware=[
            Middleware(RateLimitMiddleware),
        ],
    )

    return app


def run_streamable_http(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    app = create_app()
    logger.info("Starting Zotero MCP server (streamable-http) on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
