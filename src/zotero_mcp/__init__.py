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
        logger.info(
            "Request headers: %s",
            {k: ("***" if k.lower() == ZOTERO_API_KEY_HEADER else v) for k, v in request_obj.headers.items()},
        )
    else:
        logger.warning("No HTTP request object available in context")

    credentials = resolve_zotero_credentials(request_obj)
    return get_zotero_client_from_credentials(credentials)


def format_item(item: dict[str, Any]) -> str:
    data = item["data"]
    item_key = item["key"]
    item_type = data.get("itemType", "unknown")

    if item_type == "note":
        note_content = data.get("note", "")
        note_content = (
            note_content.replace("<p>", "").replace("</p>", "\n").replace("<br>", "\n")
        )
        note_content = note_content.replace("<strong>", "**").replace("</strong>", "**")
        note_content = note_content.replace("<em>", "*").replace("</em>", "*")

        formatted = [
            "## \U0001f4dd Note",
            f"Item Key: `{item_key}`",
        ]

        if parent_item := data.get("parentItem"):
            formatted.append(f"Parent Item: `{parent_item}`")

        if date := data.get("dateModified"):
            formatted.append(f"Last Modified: {date}")

        if tags := data.get("tags"):
            tag_list = [f"`{tag['tag']}`" for tag in tags]
            formatted.append(f"\n### Tags\n{', '.join(tag_list)}")

        formatted.append(f"\n### Note Content\n{note_content}")

        return "\n".join(formatted)

    formatted = [
        f"## {data.get('title', 'Untitled')}",
        f"Item Key: `{item_key}`",
        f"Type: {item_type}",
        f"Date: {data.get('date', 'No date')}",
    ]

    creators_by_role = {}
    for creator in data.get("creators", []):
        role = creator.get("creatorType", "contributor")
        name = ""
        if "firstName" in creator and "lastName" in creator:
            name = f"{creator['lastName']}, {creator['firstName']}"
        elif "name" in creator:
            name = creator["name"]

        if name:
            if role not in creators_by_role:
                creators_by_role[role] = []
            creators_by_role[role].append(name)

    for role, names in creators_by_role.items():
        role_display = role.capitalize() + ("s" if len(names) > 1 else "")
        formatted.append(f"{role_display}: {'; '.join(names)}")

    if publication := data.get("publicationTitle"):
        formatted.append(f"Publication: {publication}")
    if volume := data.get("volume"):
        volume_info = f"Volume: {volume}"
        if issue := data.get("issue"):
            volume_info += f", Issue: {issue}"
        if pages := data.get("pages"):
            volume_info += f", Pages: {pages}"
        formatted.append(volume_info)

    if abstract := data.get("abstractNote")):
        formatted.append(f"\n### Abstract\n{abstract}")

    if tags := data.get("tags"):
        tag_list = [f"`{tag['tag']}`" for tag in tags]
        formatted.append(f"\n### Tags\n{', '.join(tag_list)}")

    identifiers = []
    if url := data.get("url"):
        identifiers.append(f"URL: {url}")
    if doi := data.get("DOI"):
        identifiers.append(f"DOI: {doi}")
    if isbn := data.get("ISBN"):
        identifiers.append(f"ISBN: {isbn}")
    if issn := data.get("ISSN"):
        identifiers.append(f"ISSN: {issn}")

    if identifiers:
        formatted.append("\n### Identifiers\n" + "\n".join(identifiers))

    if notes := item.get("meta", {}).get("numChildren", 0):
        formatted.append(
            f"\n### Additional Information\nNumber of notes/attachments: {notes}"
        )

    return "\n".join(formatted)


def _handle_credential_error(e: Exception) -> str:
    msg = str(e)
    logger.debug("Credential error (details redacted)")
    return msg


@mcp.tool(
    name="zotero_item_metadata",
    description="Get metadata information about a specific Zotero item, given the item key.",
)
async def get_item_metadata(item_key: str, ctx: Context = None) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"
        return format_item(item)
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return (
                "Zotero API authentication failed. "
                "Please verify your API key is valid and has the required permissions. "
                "You can create a new key at https://www.zotero.org/settings/keys"
            )
        if "429" in error_msg or "rate limit" in error_msg.lower():
            return "Zotero API rate limit exceeded. Please wait a moment and try again."
        return f"Error retrieving item metadata: {error_msg}"


@mcp.tool(
    name="zotero_item_fulltext",
    description="Get the full text content of a Zotero item, given the item key of a parent item or specific attachment.",
)
async def get_item_fulltext(item_key: str, ctx: Context = None) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

        attachment = get_attachment_details(zot, item)

        header = format_item(item)

        if attachment is not None:
            attachment_info = f"\n## Attachment Information\n- **Key**: `{attachment.key}`\n- **Type**: {attachment.content_type}"

            full_text_data: Any = zot.fulltext_item(attachment.key)
            if full_text_data and "content" in full_text_data:
                item_text = full_text_data["content"]
                word_count = len(item_text.split())
                attachment_info += f"\n- **Word Count**: ~{word_count}"

                full_text = f"\n\n## Document Content\n\n{item_text}"
            else:
                full_text = "\n\n## Document Content\n\n[\u26a0\ufe0f Attachment is available but text extraction is not possible. The document may be scanned as images or have other restrictions that prevent text extraction.]"
        else:
            attachment_info = "\n\n## Attachment Information\n[\u274c No suitable attachment found for full text extraction. This item may not have any attached files or they may not be in a supported format.]"
            full_text = ""

        return f"{header}{attachment_info}{full_text}"

    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return (
                "Zotero API authentication failed. "
                "Please verify your API key is valid and has the required permissions. "
                "You can create a new key at https://www.zotero.org/settings/keys"
            )
        if "429" in error_msg or "rate limit" in error_msg.lower():
            return "Zotero API rate limit exceeded. Please wait a moment and try again."
        return f"Error retrieving item full text: {error_msg}"


@mcp.tool(
    name="zotero_search_items",
    description="Search for items in your Zotero library, given a query string, query mode (titleCreatorYear or everything), and optional tag search (supports boolean searches). Returned results can be looked up with zotero_item_fulltext or zotero_item_metadata.",
)
async def search_items(
    query: str,
    qmode: Literal["titleCreatorYear", "everything"] | None = "titleCreatorYear",
    tag: str | None = None,
    limit: int | None = 10,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        params = {"q": query, "qmode": qmode, "limit": limit}
        if tag:
            params["tag"] = tag

        zot.add_parameters(**params)
        results: Any = zot.items()

        if not results:
            return "No items found matching your query."

        header = [
            f"# Search Results for: '{query}'",
            f"Found {len(results)} items." + (f" Using tag filter: {tag}" if tag else ""),
            "Use item keys with zotero_item_metadata or zotero_item_fulltext for more details.\n",
        ]

        formatted_results = []
        for i, item in enumerate(results):
            data = item["data"]
            item_key = item.get("key", "")
            item_type = data.get("itemType", "unknown")

            if item_type == "note":
                note_content = data.get("note", "")
                note_content = (
                    note_content.replace("<p>", "")
                    .replace("</p>", "\n")
                    .replace("<br>", "\n")
                )
                note_content = note_content.replace("<strong>", "**").replace(
                    "</strong>", "**"
                )
                note_content = note_content.replace("<em>", "*").replace("</em>", "*")

                title_preview = ""
                if note_content:
                    lines = note_content.strip().split("\n")
                    first_line = lines[0].strip()
                    if first_line:
                        if len(first_line) <= 50:
                            title_preview = first_line
                        else:
                            words = first_line.split()
                            title_preview = " ".join(words[:5]) + "..."

                note_title = title_preview if title_preview else "Note"

                preview = note_content.strip()
                if len(preview) > 150:
                    preview = preview[:147] + "..."

                entry = [
                    f"## {i + 1}. \U0001f4dd {note_title}",
                    f"**Type**: Note | **Key**: `{item_key}`",
                    f"\n{preview}",
                ]

                if parent_item := data.get("parentItem"):
                    entry.insert(2, f"**Parent Item**: `{parent_item}`")

                if tags := data.get("tags"):
                    tag_list = [f"`{tag['tag']}`" for tag in tags[:5]]
                    if len(tags) > 5:
                        tag_list.append("...")
                    entry.append(f"\n**Tags**: {' '.join(tag_list)}")

                formatted_results.append("\n".join(entry))
                continue

            title = data.get("title", "Untitled")
            date = data.get("date", "")

            creators = []
            for creator in data.get("creators", [])[:3]:
                if "firstName" in creator and "lastName" in creator:
                    creators.append(f"{creator['lastName']}, {creator['firstName']}")
                elif "name" in creator:
                    creators.append(creator["name"])

            if len(data.get("creators", [])) > 3:
                creators.append("et al.")

            creator_str = "; ".join(creators) if creators else "No authors"

            source = ""
            if pub := data.get("publicationTitle"):
                source = pub
            elif book := data.get("bookTitle"):
                source = f"In: {book}"
            elif publisher := data.get("publisher"):
                source = f"{publisher}"

            abstract = data.get("abstractNote", "")
            if len(abstract) > 150:
                abstract = abstract[:147] + "..."

            entry = [
                f"## {i + 1}. {title}",
                f"**Type**: {item_type} | **Date**: {date} | **Key**: `{item_key}`",
                f"**Authors**: {creator_str}",
            ]

            if source:
                entry.append(f"**Source**: {source}")

            if abstract:
                entry.append(f"\n{abstract}")

            if tags := data.get("tags"):
                tag_list = [f"`{tag['tag']}`" for tag in tags[:5]]
                if len(tags) > 5:
                    tag_list.append("...")
                entry.append(f"\n**Tags**: {' '.join(tag_list)}")

            formatted_results.append("\n".join(entry))

        return "\n\n".join(header + formatted_results)

    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg.lower():
            return (
                "Zotero API authentication failed. "
                "Please verify your API key is valid and has the required permissions. "
                "You can create a new key at https://www.zotero.org/settings/keys"
            )
        if "429" in error_msg or "rate limit" in error_msg.lower():
            return "Zotero API rate limit exceeded. Please wait a moment and try again."
        return f"Error searching items: {error_msg}"
