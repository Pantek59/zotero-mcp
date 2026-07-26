import argparse
import logging

from zotero_mcp import set_multi_tenant_mode

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Zotero Model Context Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="Transport to use (default: streamable-http when --multi-tenant, otherwise stdio)",
    )
    parser.add_argument(
        "--multi-tenant",
        action="store_true",
        help=(
            "Enable multi-tenant mode. Reads Zotero credentials from per-request "
            "HTTP headers instead of environment variables. Implies --transport "
            "streamable-http unless overridden."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to for HTTP transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to for HTTP transports (default: 8000)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    transport = args.transport or ("streamable-http" if args.multi_tenant else "stdio")

    if args.multi_tenant and transport != "streamable-http":
        parser.error("--multi-tenant requires streamable-http transport")

    if args.multi_tenant:
        set_multi_tenant_mode(True)
        logger.info("Multi-tenant mode enabled. Credentials read from request headers.")

    if transport == "streamable-http":
        from zotero_mcp.app import run_streamable_http

        run_streamable_http(host=args.host, port=args.port)
    else:
        from zotero_mcp import mcp

        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
