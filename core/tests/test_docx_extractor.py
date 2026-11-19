"""Feature #39: real in-memory DOCX fixtures and archive/XXE guard tests."""
from __future__ import annotations

import io
import os
import stat
import zipfile

import pytest

from aura_core.filesystem.docx_extractor import extract_docx_text

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)


def parts(paragraphs=("Hello world", "Second paragraph"), *, rel=None, document=None):
    types = (f'<Types xmlns="{CT}"><Override PartName="/word/document.xml"'
             f' ContentType="{MIME}"/></Types>')
    if document is None:
        content = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        document = f'<w:document xmlns:w="{WORD}"><w:body>{content}</w:body></w:document>'
    result = {"[Content_Types].xml": types, "word/document.xml": document}
    if rel is not None:
        result["word/_rels/document.xml.rels"] = rel
    return result


def package(items, *, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, data in items.items():
            archive.writestr(name, data)
    return stream.getvalue()


def test_extract_real_paragraphs_and_integrity_hash():
    import hashlib
    blob = package(parts())
    result = extract_docx_text(blob)
    assert result.text == "Hello world\nSecond paragraph"
    assert result.paragraph_count == 2
    assert result.source_sha256 == hashlib.sha256(blob).hexdigest()
    assert result.untrusted and not result.publisher_verified
    assert not result.authorization_checked and not result.macros_executed


def test_word_tables_tabs_breaks_and_unicode():
    document = (f'<w:document xmlns:w="{WORD}"><w:body>'
                f'<w:p><w:r><w:t>Türkçe</w:t><w:tab/><w:t>Wort</w:t>'
                f'<w:br/><w:t>ok</w:t></w:r></w:p>'
                f'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell'
                f'</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                f'</w:body></w:document>')
    result = extract_docx_text(package(parts(document=document)))
    assert result.text == "Türkçe\tWort\nok\nTable cell"
    assert result.paragraph_count == 2


def test_empty_and_non_docx_payload_rejected():
    for data in (b"", b"not a zip", package({"hello.txt": "secret"})):
        with pytest.raises(ValueError):
            extract_docx_text(data)


@pytest.mark.parametrize("bad", [
    "../outside.txt", "/absolute", r"word\evil.xml",
    "word/../evil.xml",
])
def test_zip_slip_paths_rejected(bad):
    inputs = parts()
    inputs[bad] = "unsafe"
    blob = package(inputs)
    if os.name == "nt" and "\\" in bad:
        # Windows zipfile normalizes the writer's backslashes. Patch both
        # ZIP header names with equal-length raw bytes to test the actual
        # hostile archive instead of a sanitized archive created by Python.
        normalized = bad.replace("\\", "/").encode("ascii")
        raw_name = bad.encode("ascii")
        assert blob.count(normalized) == 2
        blob = blob.replace(normalized, raw_name)
    with pytest.raises(ValueError, match="unsafe"):
        extract_docx_text(blob)


def test_duplicate_paths_and_symlink_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in parts().items():
            archive.writestr(name, data)
        archive.writestr("WORD/DOCUMENT.XML", "duplicate")
    with pytest.raises(ValueError, match="duplicate"):
        extract_docx_text(stream.getvalue())

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in parts().items():
            archive.writestr(name, data)
        link = zipfile.ZipInfo("word/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../secrets")
    with pytest.raises(ValueError, match="symlinks"):
        extract_docx_text(stream.getvalue())


def test_reject_macro_and_embedded_object():
    for name in ("word/vbaProject.bin", "word/embeddings/blob.bin"):
        inputs = parts()
        inputs[name] = "binary"
        with pytest.raises(ValueError, match="macro or embedded"):
            extract_docx_text(package(inputs))


def test_reject_external_document_relationship():
    rel = (f'<Relationships xmlns="{REL}"><Relationship Id="r1"'
           ' Type="http://schemas.openxmlformats.org/officeDocument/2006/'
           'relationships/hyperlink" Target="https://example.org/"'
           ' TargetMode="External"/></Relationships>')
    with pytest.raises(ValueError, match="external DOCX"):
        extract_docx_text(package(parts(rel=rel)))


def test_reject_dtd_and_entity_declarations():
    malicious = (
        f'<!DOCTYPE w:document [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f'<w:document xmlns:w="{WORD}"><w:body>'
        f'<w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>'
    )
    with pytest.raises(ValueError, match="DTD"):
        extract_docx_text(package(parts(document=malicious)))


def test_wrong_content_type_and_xml_rejected():
    source = parts()
    source["[Content_Types].xml"] = source["[Content_Types].xml"].replace(
        "wordprocessingml.document.main+xml", "wordprocessingml.document.macroEnabled.main+xml"
    )
    with pytest.raises(ValueError, match="non-macro"):
        extract_docx_text(package(source))
    with pytest.raises(ValueError, match="Invalid DOCX XML"):
        extract_docx_text(package(parts(document="<not-closed")))


def test_compression_bomb_and_bounds_rejected():
    inputs = parts()
    inputs["word/bloat.txt"] = "A" * 400000
    with pytest.raises(ValueError, match="expansion ratio"):
        extract_docx_text(package(inputs))
    blob = package(parts(paragraphs=("long text", "another paragraph")))
    with pytest.raises(ValueError, match="text exceeds budget"):
        extract_docx_text(blob, max_chars=5)
    with pytest.raises(ValueError, match="paragraph budget"):
        extract_docx_text(blob, max_paragraphs=1)


@pytest.mark.parametrize("kwargs", [
    {"max_chars": True}, {"max_chars": 0}, {"max_chars": 100001},
    {"max_paragraphs": False}, {"max_paragraphs": 5001},
])
def test_invalid_budgets_rejected(kwargs):
    with pytest.raises(ValueError):
        extract_docx_text(package(parts()), **kwargs)


def test_prohibit_path_and_bytearray_input():
    for payload in ("/tmp/private.docx", bytearray(package(parts()))):
        with pytest.raises(ValueError):
            extract_docx_text(payload)
