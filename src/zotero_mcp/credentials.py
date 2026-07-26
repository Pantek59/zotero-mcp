import hashlib
import logging
from dataclasses import dataclass

from starlette.requests import Request

logger = logging.getLogger(__name__)


class MissingCredentialsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


ZOTERO_API_KEY_HEADER = "x-zotero-api-key"
ZOTERO_LIBRARY_ID_HEADER = "x-zotero-library-id"
ZOTERO_LIBRARY_TYPE_HEADER = "x-zotero-library-type"

HEADER_NAMES = {
    ZOTERO_API_KEY_HEADER: "X-Zotero-Api-Key",
    ZOTERO_LIBRARY_ID_HEADER: "X-Zotero-Library-Id",
    ZOTERO_LIBRARY_TYPE_HEADER: "X-Zotero-Library-Type",
}


@dataclass(frozen=True)
class ZoteroCredentials:
    api_key: str
    library_id: str
    library_type: str = "user"

    @property
    def cache_key(self) -> str:
        key_hash = hashlib.sha256(self.api_key.encode()).hexdigest()
        return f"{key_hash}:{self.library_id}:{self.library_type}"


def resolve_zotero_credentials(context_request: Request | None) -> ZoteroCredentials:
    if context_request is None:
        raise MissingCredentialsError(
            "Zotero credentials missing or invalid. "
            "Configure your Zotero API key in LibreChat's MCP settings."
        )

    api_key = context_request.headers.get(ZOTERO_API_KEY_HEADER)
    library_id = context_request.headers.get(ZOTERO_LIBRARY_ID_HEADER)
    library_type = context_request.headers.get(ZOTERO_LIBRARY_TYPE_HEADER, "user")

    unsubstituted = []
    if api_key and api_key.startswith("${"):
        unsubstituted.append(ZOTERO_API_KEY_HEADER)
    if library_id and library_id.startswith("${"):
        unsubstituted.append(ZOTERO_LIBRARY_ID_HEADER)
    if library_type and library_type.startswith("${"):
        unsubstituted.append(ZOTERO_LIBRARY_TYPE_HEADER)

    if unsubstituted:
        raise MissingCredentialsError(
            "Zotero credentials missing or invalid. "
            "Header variable substitution failed - the following headers still "
            "contain literal ${...} templates: "
            f"{', '.join(unsubstituted)}. "
            "Ensure your MCP client (e.g. LibreChat) substitutes these variables, "
            "or hardcode the values directly in the configuration."
        )

    logger.info(
        "Resolved headers: api_key=%s, library_id=%r, library_type=%r",
        "***" if api_key else None,
        library_id,
        library_type,
    )

    missing = []
    if not api_key or not api_key.strip():
        missing.append(HEADER_NAMES[ZOTERO_API_KEY_HEADER])
    if not library_id or not library_id.strip():
        missing.append(HEADER_NAMES[ZOTERO_LIBRARY_ID_HEADER])

    if missing:
        raise MissingCredentialsError(
            "Zotero credentials missing or invalid. "
            "Configure your Zotero API key in LibreChat's MCP settings. "
            f"Missing headers: {', '.join(missing)}"
        )

    if not library_id.isdigit():
        raise InvalidCredentialsError(
            "Zotero credentials missing or invalid. "
            "X-Zotero-Library-Id must be numeric."
        )

    if library_type not in ("user", "group"):
        raise InvalidCredentialsError(
            "Zotero credentials missing or invalid. "
            "X-Zotero-Library-Type must be 'user' or 'group'."
        )

    return ZoteroCredentials(
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
    )