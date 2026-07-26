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
        api_key_val = request_obj.headers.get(ZOTERO_API_KEY_HEADER, "")
        logger.info(
            "Request headers: api_key_prefix=%s..., library_id=%r, library_type=%r",
            api_key_val[:4] if len(api_key_val) >= 4 else "(short)",
            request_obj.headers.get("x-zotero-library-id"),
            request_obj.headers.get("x-zotero-library-type"),
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

        parent_item = data.get("parentItem")
        if parent_item:
            formatted.append(f"Parent Item: `{parent_item}`")

        date = data.get("dateModified")
        if date:
            formatted.append(f"Last Modified: {date}")

        tags = data.get("tags")
        if tags:
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

    publication = data.get("publicationTitle")
    if publication:
        formatted.append(f"Publication: {publication}")
    volume = data.get("volume")
    if volume:
        volume_info = f"Volume: {volume}"
        issue = data.get("issue")
        if issue:
            volume_info += f", Issue: {issue}"
        pages = data.get("pages")
        if pages:
            volume_info += f", Pages: {pages}"
        formatted.append(volume_info)

    abstract = data.get("abstractNote")
    if abstract:
        formatted.append(f"\n### Abstract\n{abstract}")

    tags = data.get("tags")
    if tags:
        tag_list = [f"`{tag['tag']}`" for tag in tags]
        formatted.append(f"\n### Tags\n{', '.join(tag_list)}")

    identifiers = []
    url = data.get("url")
    if url:
        identifiers.append(f"URL: {url}")
    doi = data.get("DOI")
    if doi:
        identifiers.append(f"DOI: {doi}")
    isbn = data.get("ISBN")
    if isbn:
        identifiers.append(f"ISBN: {isbn}")
    issn = data.get("ISSN")
    if issn:
        identifiers.append(f"ISSN: {issn}")

    if identifiers:
        formatted.append("\n### Identifiers\n" + "\n".join(identifiers))

    notes = item.get("meta", {}).get("numChildren", 0)
    if notes:
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
            attachment_info = (
                f"\n## Attachment Information\n"
                f"- **Key**: `{attachment.key}`\n"
                f"- **Type**: {attachment.content_type}"
            )

            full_text_data: Any = zot.fulltext_item(attachment.key)
            if full_text_data and "content" in full_text_data:
                item_text = full_text_data["content"]
                word_count = len(item_text.split())
                attachment_info += f"\n- **Word Count**: ~{word_count}"

                full_text = f"\n\n## Document Content\n\n{item_text}"
            else:
                full_text = (
                    "\n\n## Document Content\n\n"
                    "[\u26a0\ufe0f Attachment is available but text extraction is not possible. "
                    "The document may be scanned as images or have other restrictions "
                    "that prevent text extraction.]"
                )
        else:
            attachment_info = (
                "\n\n## Attachment Information\n"
                "[\u274c No suitable attachment found for full text extraction. "
                "This item may not have any attached files or they may not be in a "
                "supported format.]"
            )
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
    description=(
        "Search for items in your Zotero library, given a query string, "
        "query mode (titleCreatorYear or everything), and optional tag search "
        "(supports boolean searches). Returned results can be looked up with "
        "zotero_item_fulltext or zotero_item_metadata."
    ),
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
            f"Found {len(results)} items."
            + (f" Using tag filter: {tag}" if tag else ""),
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

                parent_item = data.get("parentItem")
                if parent_item:
                    entry.insert(2, f"**Parent Item**: `{parent_item}`")

                tags = data.get("tags")
                if tags:
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
            pub = data.get("publicationTitle")
            if pub:
                source = pub
            else:
                book = data.get("bookTitle")
                if book:
                    source = f"In: {book}"
                else:
                    publisher = data.get("publisher")
                    if publisher:
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

            tags = data.get("tags")
            if tags:
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


def _handle_error(e: Exception) -> str:
    error_msg = str(e)
    if "403" in error_msg or "Forbidden" in error_msg.lower():
        return (
            "Zotero API authentication failed. "
            "Please verify your API key is valid and has the required permissions. "
            "You can create a new key at https://www.zotero.org/settings/keys"
        )
    if "429" in error_msg or "rate limit" in error_msg.lower():
        return "Zotero API rate limit exceeded. Please wait a moment and try again."
    return f"Error: {error_msg}"


@mcp.tool(
    name="zotero_list_collections",
    description="List all collections in the Zotero library, including their hierarchy.",
)
async def list_collections(ctx: Context = None) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        collections: Any = zot.all_collections()
        if not collections:
            return "No collections found in this library."

        lines = ["# Collections"]
        for coll in collections:
            data = coll["data"]
            depth = data.get("depth", 0)
            indent = "  " * depth
            key = data["key"]
            name = data["name"]
            parent = data.get("parentCollection", "")
            parent_str = f" (parent: `{parent}`)" if parent else ""
            lines.append(f"{indent}- **{name}** `{key}`{parent_str}")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_get_item_template",
    description="Get the field template for a Zotero item type. Use this before creating items to know which fields are available and required for a given item type (e.g. 'journalArticle', 'book', 'note', 'attachment').",
)
async def get_item_template(
    item_type: str,
    link_mode: str | None = None,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        template: Any = zot.item_template(item_type, link_mode)
        if not template:
            return f"No template found for item type: {item_type}"

        lines = [f"## Template for `{item_type}`"]

        required = template.get("required", [])
        if required:
            lines.append(
                f"\n### Required fields\n{', '.join(f'`{f}`' for f in required)}"
            )

        optional_fields = []
        for key, value in sorted(template.items()):
            if key in (
                "itemType",
                "required",
                "version",
                "key",
                "collections",
                "dateAdded",
                "dateModified",
                "relations",
                "dateModified",
                "accessDate",
                "tags",
            ):
                continue
            if key not in required:
                optional_fields.append(key)

        if optional_fields:
            lines.append(
                f"\n### Optional fields\n{', '.join(f'`{f}`' for f in optional_fields)}"
            )

        lines.append(f"\n### Full template\n```json\n{_format_json(template)}\n```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


def _format_json(obj: dict, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent
    for key, value in sorted(obj.items()):
        if isinstance(value, dict):
            lines.append(f'{prefix}"{key}": {{')
            lines.append(_format_json(value, indent + 1))
            lines.append(f"{prefix}}}")
        elif isinstance(value, list):
            lines.append(f'{prefix}"{key}": {value}')
        elif isinstance(value, bool):
            lines.append(f'{prefix}"{key}": {str(value).lower()}')
        elif value is None:
            lines.append(f'{prefix}"{key}": null')
        else:
            lines.append(f'{prefix}"{key}": {repr(value)}')
    return "\n".join(lines)


@mcp.tool(
    name="zotero_create_items",
    description=(
        "Create one or more items in the Zotero library. "
        "Each item must include at minimum 'itemType' and the required fields for that type. "
        "Use zotero_get_item_template first to determine the required fields. "
        "To create a note, set itemType to 'note' and include 'note' and 'parentItem' fields. "
        "To create a linked URL attachment, set itemType to 'attachment', linkMode to 'linked_url', "
        "and include 'url' and 'title' fields."
    ),
)
async def create_items(
    items_json: str,
    parent_id: str | None = None,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        import json

        payload = json.loads(items_json)
        if isinstance(payload, dict):
            payload = [payload]

        if len(payload) > 50:
            return "Error: You can create a maximum of 50 items per call."

        result: Any = zot.create_items(payload, parentid=parent_id)

        successful = result.get("success", {})
        failed = result.get("failed", {})
        unchanged = result.get("unchanged", {})

        lines = [f"## Created {len(successful)} item(s)"]

        for key, item_key in successful.items():
            idx = int(key)
            item_type = payload[idx].get("itemType", "unknown")
            title = (
                payload[idx].get("title", payload[idx].get("note", "")[:50])
                or "Untitled"
            )
            lines.append(f"- `{item_key}` ({item_type}): {title}")

        if failed:
            lines.append(f"\n### Failed ({len(failed)} item(s))")
            for key, error in failed.items():
                lines.append(f"- Item {key}: {error}")

        if unchanged:
            lines.append(f"\n### Unchanged ({len(unchanged)} item(s))")
            for key, item_key in unchanged.items():
                lines.append(f"- `{item_key}`: already exists")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_update_item",
    description=(
        "Update an existing Zotero item's metadata. "
        "Provide the item key and a JSON object with the fields to update. "
        "You only need to include the fields you want to change plus the 'key' and 'version' fields. "
        "Use zotero_item_metadata to get the current item data including its version."
    ),
)
async def update_item(
    item_key: str,
    version: int,
    updates_json: str,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        import json

        updates = json.loads(updates_json)
        updates["key"] = item_key
        updates["version"] = version

        response = zot.update_item(updates)

        if hasattr(response, "status_code") and response.status_code == 204:
            return f"Successfully updated item `{item_key}`."
        if hasattr(response, "json"):
            try:
                data = response.json()
                return f"Successfully updated item `{item_key}`. Version: {data.get('version', 'unknown')}"
            except Exception:
                return f"Successfully updated item `{item_key}`."

        return f"Successfully updated item `{item_key}`."

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_delete_item",
    description=(
        "Move an item to the Zotero trash. This is safer than permanent deletion "
        "because the item can be recovered from the trash. "
        "Provide the item key and its current version."
    ),
)
async def delete_item(
    item_key: str,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

        item["data"]["deleted"] = 1
        zot.update_item(item["data"])
        return f"Successfully moved item `{item_key}` to trash."

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_create_collection",
    description=(
        "Create a new collection in the Zotero library. "
        "Provide the collection name and optionally a parent collection key to create a sub-collection."
    ),
)
async def create_collection(
    name: str,
    parent_collection_key: str | None = None,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        payload = [{"name": name}]
        if parent_collection_key:
            payload[0]["parentCollection"] = parent_collection_key

        result: Any = zot.create_collections(payload)

        successful = result.get("success", {})
        failed = result.get("failed", {})

        if successful:
            keys = list(successful.values())
            lines = ["## Created collection"]
            for collection_key in keys:
                lines.append(f"- **{name}** `{collection_key}`")
                if parent_collection_key:
                    lines.append(f"  Parent: `{parent_collection_key}`")
            return "\n".join(lines)

        if failed:
            return f"Failed to create collection: {failed}"

        return "Collection creation returned no result."

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_add_tags",
    description="Add one or more tags to a Zotero item. Provide the item key and a comma-separated list of tags.",
)
async def add_tags(
    item_key: str,
    tags: str,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            return "No tags provided. Please provide a comma-separated list of tags."

        result = zot.add_tags(item, *tag_list)

        if hasattr(result, "json"):
            try:
                updated = result.json()
                current_tags = updated.get("data", {}).get("tags", [])
                tag_names = [t["tag"] for t in current_tags]
                return f"Successfully added tags to `{item_key}`. Current tags: {', '.join(tag_names)}"
            except Exception:
                pass

        return f"Successfully added tags {', '.join(tag_list)} to `{item_key}`."

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="zotero_add_to_collection",
    description="Add an item to a collection. Provide the item key and the collection key.",
)
async def add_to_collection(
    item_key: str,
    collection_key: str,
    ctx: Context = None,
) -> str:
    try:
        zot = _get_zotero_client(ctx)
    except (MissingCredentialsError, InvalidCredentialsError) as e:
        return _handle_credential_error(e)

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

        zot.addto_collection(collection_key, item)
        return f"Successfully added item `{item_key}` to collection `{collection_key}`."

    except Exception as e:
        return _handle_error(e)
