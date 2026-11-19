"""Read-only bounded RFC822/MIME preview from already-authorized bytes.

Never opens an inbox, follows links, downloads attachments, sends messages,
runs HTML, or calls a provider/Gateway. All resulting text is untrusted.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from itertools import islice

_MAX_BYTES = 512 * 1024
_MAX_PARTS = 32
_MAX_BODY_CHARS = 100_000
_MAX_ATTACHMENTS = 20
_MAX_ATTACHMENT_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class AttachmentDescriptor:
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    content_exposed: bool = False


@dataclass(frozen=True, slots=True)
class EmailPreview:
    sender: str
    recipients: str
    subject: str
    text_body: str
    attachments: tuple[AttachmentDescriptor, ...]
    source_sha256: str
    html_omitted: bool
    untrusted: bool = True
    authorization_checked: bool = False
    delivery_verified: bool = False
    attachments_opened: bool = False
    sent: bool = False


def _label(value: object, *, max_len: int) -> str:
    if type(value) is not str or len(value) > max_len:
        raise ValueError("invalid email header or filename")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("control character in email metadata")
    return value.strip()


def _single_header(message: Message, name: str, max_len: int) -> str:
    entries = message.get_all(name, [])
    if len(entries) > 1:
        raise ValueError("ambiguous duplicate email header")
    return _label(str(entries[0]) if entries else "", max_len=max_len)


def preview_eml(raw: bytes, *, max_parts: int = _MAX_PARTS) -> EmailPreview:
    """Inspect an RFC822/MIME envelope without fetching or executing content."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
        raise ValueError("bounded email bytes required")
    if type(max_parts) is not int or not 1 <= max_parts <= _MAX_PARTS:
        raise ValueError("max_parts must be 1..32")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except (ValueError, UnicodeError, RecursionError, MemoryError) as exc:
        raise ValueError("invalid email envelope") from exc
    if message.defects:
        raise ValueError("defective email envelope")
    sender = _single_header(message, "From", 320)
    recipients = _single_header(message, "To", 800)
    subject = _single_header(message, "Subject", 300)
    parts = list(islice(message.walk(), max_parts + 1))
    if len(parts) > max_parts:
        raise ValueError("MIME part budget exceeded")
    if any(part.defects for part in parts):
        raise ValueError("defective MIME content")
    attachments: list[AttachmentDescriptor] = []
    body: str | None = None
    html_omitted = False
    for part in parts:
        if part.is_multipart():
            continue
        media_type = part.get_content_type().lower()
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition == "attachment" or filename is not None:
            if len(attachments) >= _MAX_ATTACHMENTS:
                raise ValueError("too many attachments")
            safe_filename = _label(filename or "unnamed", max_len=120)
            if not safe_filename or safe_filename in {".", ".."} or any(
                char in safe_filename for char in "/\\:"
            ):
                raise ValueError("unsafe attachment filename")
            data = part.get_payload(decode=True)
            if not isinstance(data, bytes) or len(data) > _MAX_ATTACHMENT_BYTES:
                raise ValueError("invalid or oversized attachment")
            attachments.append(AttachmentDescriptor(
                filename=safe_filename,
                media_type=_label(media_type, max_len=120),
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            ))
            continue
        if media_type == "text/html":
            html_omitted = True
            continue
        if media_type != "text/plain":
            continue
        if body is not None:
            raise ValueError("ambiguous multiple plain-text bodies")
        try:
            content = part.get_content()
        except (LookupError, UnicodeError, ValueError, TypeError) as exc:
            raise ValueError("unsupported email text encoding") from exc
        if type(content) is not str or len(content) > _MAX_BODY_CHARS:
            raise ValueError("email text body exceeds size budget")
        body = content
    return EmailPreview(
        sender=sender, recipients=recipients, subject=subject,
        text_body=body or "", attachments=tuple(attachments),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        html_omitted=html_omitted,
    )
