import logging
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pyzotero import zotero as zotero_module

from zotero_mcp.client import get_attachment_details
from zotero_mcp.client_factory import (
    get_zotero_client_from_credentials,
    get_zotero_client_from_env,
)
from zotero_mcp.credentials import (
    ZOTERO_API_KEY_HEADER,
    InvalidCredentialsError,
    MissingCredentialsError,
    resolve_zotero_credentials,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("Zotero")

_MULTI_TENANT_MODE = False


def set_multi_tenant_mode(enabled: bool) -> None:
    global _MULTI_TENANT_MODE
    _MULTI_TENANT_MODE = enabled
    if enabled:
        from mcp.server.fastmcp.server import TransportSecuritySettings

        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
        logger.info(
            "Running in multi-tenant/header mode. "
            "Per-request X-Zotero-* headers are required."
        )


def is_multi_tenant() -> bool:
    return _MULTI_TENANT_MODE


def _get_zotero_client(ctx: Context | None = None) -> zotero_module.Zotero:
    if not is_multi_tenant():
        return get_zotero_client_from_env()

    if ctx is None:
        raise MissingCredentialsError(
            "Zotero credentials missing or invalid. "
            "Configure your Zotero API key in LibreChat's MCP settings."
        )

    request_obj = None
    if ctx.request_context is not None:
        request_obj = ctx.request_context.request

    if request_obj is not None:
        logger.debug(
            "Request headers: %s",
            {k: ("***" if k.lower() == ZOTERO_API_KEY_HEADER else v) for k, v in request_obj.headers.items()},
        )
    else:
        logger.warning("No HTTP request object available in context")

    credentials = resolve_zotero_credentials(request_obj)
    return get_zotero_client_from_credentials(credentials)
