from typing import Any

from pydantic import BaseModel
from pyzotero import zotero


class AttachmentDetails(BaseModel):
    key: str
    content_type: str


def get_attachment_details(
    zot: zotero.Zotero,
    item: dict[str, Any],
) -> AttachmentDetails | None:
    data = item.get("data", {})
    item_type = data.get("itemType")

    if item_type == "attachment":
        content_type = data.get("contentType")
        return AttachmentDetails(
            key=data.get("key"),
            content_type=content_type,
        )

    try:
        children: Any = zot.children(data.get("key", ""))
        pdfs = []
        htmls = []
        others = []

        for child in children:
            child_data = child.get("data", {})
            if child_data.get("itemType") == "attachment":
                content_type = child_data.get("contentType")
                file_size = child_data.get("md5", "")

                if content_type == "application/pdf":
                    pdfs.append((child_data.get("key"), content_type, file_size))
                elif content_type == "text/html":
                    htmls.append((child_data.get("key"), content_type, file_size))
                else:
                    others.append((child_data.get("key"), content_type, file_size))

        if pdfs:
            pdfs.sort(key=lambda x: x[2], reverse=True)
            return AttachmentDetails(
                key=pdfs[0][0],
                content_type=pdfs[0][1],
            )
        if htmls:
            htmls.sort(key=lambda x: x[2], reverse=True)
            return AttachmentDetails(
                key=htmls[0][0],
                content_type=htmls[0][1],
            )
        if others:
            others.sort(key=lambda x: x[2], reverse=True)
            return AttachmentDetails(
                key=others[0][0],
                content_type=others[0][1],
            )
    except Exception:
        pass

    return None
