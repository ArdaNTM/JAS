"""Offline, bounded DOCX text extraction from already-authorized bytes.

This parser does not open filesystem paths, fetch URLs, execute macros, follow
relationships, or grant an MCP capability. All document text is untrusted data.
"""
from __future__ import annotations

import hashlib
import io
import re
import stat
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOCUMENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)
_MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED = 8 * 1024 * 1024
_MAX_XML_BYTES = 2 * 1024 * 1024
_MAX_MEMBERS = 128
_DTD = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DocxText:
    text: str
    paragraph_count: int
    source_sha256: str
    untrusted: bool = True
    publisher_verified: bool = False
    authorization_checked: bool = False
    macros_executed: bool = False


def _xml(data: bytes, label: str) -> ET.Element:
    if len(data) > _MAX_XML_BYTES:
        raise ValueError("DOCX XML part exceeds size limit")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("DOCX XML must be UTF-8") from exc
    if _DTD.search(decoded):
        raise ValueError("DTD or entity declarations are prohibited")
    try:
        root = ET.fromstring(decoded)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("Invalid DOCX XML") from exc
    if sum(1 for _ in root.iter()) > 25000:
        raise ValueError("DOCX XML has too many elements")
    return root


def extract_docx_text(
    payload: bytes, *, max_chars: int = 100000, max_paragraphs: int = 5000
) -> DocxText:
    """Read standard Word paragraphs in document order, without IO side effects.

    The caller must authenticate the principal and authorize the original
    file read through existing AURA PermissionEngine and MCP Gateway. This
    function intentionally cannot act as that authorization boundary.
    """
    if type(payload) is not bytes or not 1 <= len(payload) <= _MAX_ARCHIVE_BYTES:
        raise ValueError("bounded DOCX bytes required")
    if type(max_chars) is not int or not 1 <= max_chars <= 100000:
        raise ValueError("max_chars must be 1..100000")
    if type(max_paragraphs) is not int or not 1 <= max_paragraphs <= 5000:
        raise ValueError("max_paragraphs must be 1..5000")
    archive_bytes = io.BytesIO(payload)
    try:
        with zipfile.ZipFile(archive_bytes, mode="r") as archive:
            members = archive.infolist()
            if not 2 <= len(members) <= _MAX_MEMBERS:
                raise ValueError("DOCX package member count invalid")
            known: dict[str, zipfile.ZipInfo] = {}
            uncompressed = 0
            for item in members:
                # ZipInfo.filename may normalize backslashes on Windows.
                # orig_filename retains the raw ZIP name for traversal checks.
                name = item.orig_filename
                parts = name.rstrip("/").split("/")
                if (
                    not name or len(name) > 256 or "\\" in name
                    or name.startswith("/") or any(p in {"", ".", ".."} for p in parts)
                    or any(ord(char) < 32 or ord(char) == 127 for char in name)
                ):
                    raise ValueError("unsafe DOCX package path")
                if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("DOCX package symlinks are forbidden")
                if item.flag_bits & 1 or item.compress_type not in (
                    zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED
                ):
                    raise ValueError("encrypted or unsupported DOCX member")
                if item.file_size > 4 * 1024 * 1024 or item.compress_size < 0:
                    raise ValueError("DOCX package member exceeds size limit")
                if item.file_size > max(1, item.compress_size) * 100:
                    raise ValueError("DOCX expansion ratio exceeds limit")
                uncompressed += item.file_size
                if uncompressed > _MAX_TOTAL_UNCOMPRESSED:
                    raise ValueError("DOCX package exceeds uncompressed budget")
                lowered = name.casefold()
                if lowered in known:
                    raise ValueError("ambiguous duplicate DOCX path")
                if any(marker in lowered for marker in (
                    "vbaproject", "/activex/", "/embeddings/", "oleobject"
                )):
                    raise ValueError("macro or embedded executable content denied")
                known[lowered] = item
            required = ("[content_types].xml", "word/document.xml")
            if not all(name in known for name in required):
                raise ValueError("standard Word document part missing")

            def read_xml(name: str) -> ET.Element:
                info = known[name]
                if info.file_size > _MAX_XML_BYTES:
                    raise ValueError("DOCX XML part exceeds size limit")
                with archive.open(info) as stream:
                    raw = stream.read(_MAX_XML_BYTES + 1)
                return _xml(raw, name)

            types = read_xml("[content_types].xml")
            if types.tag != f"{{{_CONTENT_TYPES}}}Types":
                raise ValueError("invalid DOCX content types")
            matches = [
                item.attrib.get("ContentType")
                for item in types.findall(f"{{{_CONTENT_TYPES}}}Override")
                if item.attrib.get("PartName") == "/word/document.xml"
            ]
            if matches != [_DOCUMENT_TYPE]:
                raise ValueError("DOCX is not a standard non-macro Word document")
            for name in known:
                if name.endswith(".rels"):
                    relationships = read_xml(name)
                    if relationships.tag != f"{{{_RELATIONSHIPS}}}Relationships":
                        raise ValueError("invalid DOCX relationships")
                    for rel in relationships:
                        if rel.attrib.get("TargetMode", "").casefold() == "external":
                            raise ValueError("external DOCX relationship denied")

            root = read_xml("word/document.xml")
            if root.tag != f"{{{_WORD}}}document":
                raise ValueError("invalid Word document root")
            body = root.find(f"{{{_WORD}}}body")
            if body is None:
                raise ValueError("Word document body missing")
            paragraphs: list[str] = []
            length = 0
            count = 0
            for paragraph in body.iter(f"{{{_WORD}}}p"):
                count += 1
                if count > max_paragraphs:
                    raise ValueError("DOCX paragraph budget exceeded")
                chunks: list[str] = []
                for node in paragraph.iter():
                    if node.tag == f"{{{_WORD}}}t" and node.text:
                        chunks.append(node.text)
                    elif node.tag == f"{{{_WORD}}}tab":
                        chunks.append("\t")
                    elif node.tag in (f"{{{_WORD}}}br", f"{{{_WORD}}}cr"):
                        chunks.append("\n")
                line = "".join(chunks)
                length += len(line) + (1 if paragraphs else 0)
                if length > max_chars:
                    raise ValueError("DOCX extracted text exceeds budget")
                paragraphs.append(line)
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
        raise ValueError("invalid or unsupported DOCX archive") from exc

    return DocxText(
        text="\n".join(paragraphs),
        paragraph_count=count,
        source_sha256=hashlib.sha256(payload).hexdigest(),
    )
