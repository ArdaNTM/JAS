"""Deterministic cited research report as Markdown and real DOCX bytes.

Authored observations and citations are untrusted. Every DOI must already be
present in the reconciled citation inventory, and metadata conflicts fail
closed; report generation does not certify publisher authenticity.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

from aura_core.research.citations import CitationReview, render_bibliography

_MAX_SECTIONS = 20
_MAX_CHARS = 120_000
_BAD_XML = {0xFFFE, 0xFFFF}


def _safe(value: str, *, limit: int, label: str) -> str:
    if (type(value) is not str or not value.strip() or len(value) > limit or
        any((ord(ch) < 32 and ch not in "\n\t") or
            0xD800 <= ord(ch) <= 0xDFFF or ord(ch) in _BAD_XML
            for ch in value)):
        raise ValueError(f"{label} must be bounded valid nonempty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ReportSection:
    heading: str
    body: str
    cited_dois: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourcedReport:
    title: str
    sections: tuple[ReportSection, ...]
    cited_reviews: tuple[CitationReview, ...]
    sha256: str
    source_authenticity_verified: bool = False
    owner_approved: bool = False
    untrusted: bool = True

    def markdown(self) -> str:
        from aura_core.research.citations import _escape_markdown
        lines = ["# " + _escape_markdown(self.title), "",
                 "> AURA offline research draft. Sources and claims are untrusted;",
                 "> provider authenticity and Owner acceptance are NOT verified.", ""]
        for section in self.sections:
            lines.extend(["## " + _escape_markdown(section.heading), "",
                          _escape_markdown(section.body), "",
                          "References: " + ", ".join(section.cited_dois), ""])
        lines.extend(["## Bibliography", "", render_bibliography(self.cited_reviews), ""])
        return "\n".join(lines)

    def docx(self) -> bytes:
        """Produce a deterministic, macros-free local WordprocessingML document."""
        paragraphs = [
            self.title,
            "AURA offline research draft — source authenticity and Owner approval not verified.",
        ]
        for section in self.sections:
            paragraphs.extend((
                section.heading, section.body,
                "References: " + ", ".join(section.cited_dois),
            ))
        paragraphs.append("Bibliography")
        paragraphs.extend(render_bibliography(self.cited_reviews).splitlines())
        if sum(len(x) for x in paragraphs) > _MAX_CHARS:
            raise ValueError("Word report exceeds bounded size")
        body = "".join(
            '<w:p><w:r><w:t xml:space="preserve">' + escape(paragraph) +
            '</w:t></w:r></w:p>'
            for paragraph in paragraphs
        )
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>' + body + '<w:sectPr/></w:body></w:document>'
        )
        types = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="'
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        )
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, source in (
                ("[Content_Types].xml", types),
                ("_rels/.rels", rels),
                ("word/document.xml", document),
            ):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                z.writestr(info, source.encode("utf-8"))
        output = data.getvalue()
        if len(output) > 2_000_000:
            raise ValueError("Word report byte budget exceeded")
        return output


def author_research_report(
    *, title: str, sections: tuple[ReportSection, ...],
    citations: tuple[CitationReview, ...],
) -> SourcedReport:
    """Reject unsupported references and metadata conflicts; never fetch URLs."""
    headline = _safe(title, limit=160, label="report title")
    if type(sections) is not tuple or not 1 <= len(sections) <= _MAX_SECTIONS:
        raise ValueError("1..20 report sections required")
    if type(citations) is not tuple or not 1 <= len(citations) <= 50:
        raise ValueError("1..50 citations required")
    citations_by_doi = {}
    for citation in citations:
        if type(citation) is not CitationReview or citation.conflicting_metadata:
            raise ValueError("conflicting or invalid source metadata must be reviewed first")
        if citation.doi in citations_by_doi:
            raise ValueError("duplicate DOI")
        citations_by_doi[citation.doi] = citation
    normalized = []
    body_size = len(headline)
    cited = set()
    for item in sections:
        if type(item) is not ReportSection or type(item.cited_dois) is not tuple:
            raise ValueError("invalid section")
        heading = _safe(item.heading, limit=160, label="section heading")
        body = _safe(item.body, limit=8000, label="section body")
        body_size += len(heading) + len(body)
        if body_size > _MAX_CHARS:
            raise ValueError("report content budget exceeded")
        if not 1 <= len(item.cited_dois) <= 15:
            raise ValueError("each claim section needs references")
        for doi in item.cited_dois:
            if type(doi) is not str or doi not in citations_by_doi:
                raise ValueError("claim references unreviewed DOI")
            cited.add(doi)
        normalized.append(ReportSection(heading, body, tuple(sorted(set(item.cited_dois)))))
    used = tuple(citations_by_doi[doi] for doi in sorted(cited))
    material = json.dumps(
        {"title": headline, "sections": [
            (s.heading, s.body, s.cited_dois) for s in normalized
        ], "dois": [s.doi for s in used]},
        ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return SourcedReport(
        title=headline, sections=tuple(normalized), cited_reviews=used,
        sha256=hashlib.sha256(material.encode("utf-8")).hexdigest(),
    )


def author_archived_research_report(
    *, archive: object, principal_id: str, title: str,
    sources: tuple[tuple[str, str], ...],
    citations: tuple[CitationReview, ...],
) -> SourcedReport:
    """Create a real DOCX-capable report from integrity-checked archive bytes.

    A caller must independently authenticate the principal and authorize archive
    access; this pure orchestration does not certify publisher identity.
    """
    from aura_core.research.archive import SQLiteResearchArchive
    if type(archive) is not SQLiteResearchArchive:
        raise ValueError("existing scoped archive required")
    if type(principal_id) is not str or not principal_id.strip() or len(principal_id) > 200:
        raise ValueError("authenticated principal must be supplied by trusted caller")
    if type(sources) is not tuple or not 1 <= len(sources) <= 20:
        raise ValueError("1..20 reviewed archive references required")
    reviewed = {item.doi for item in citations if type(item) is CitationReview
                and not item.conflicting_metadata}
    if len(reviewed) != len(citations):
        raise ValueError("conflicting or duplicate cited DOI")
    seen: set[str] = set()
    sections: list[ReportSection] = []
    for archive_id, doi in sources:
        if (type(archive_id) is not str or archive_id in seen or
                type(doi) is not str or doi not in reviewed):
            raise ValueError("invalid or duplicate verified archive reference")
        seen.add(archive_id)
        archived = archive.get(principal_id=principal_id, archive_id=archive_id)
        if archived is None:
            raise PermissionError("archive source is not visible in this principal scope")
        content = archived["content"]
        if type(content) is not str or not content.strip() or len(content) > 7000:
            raise ValueError("archive source must be bounded nonempty text")
        # Untrusted archive text is quoted/attributed, never executed or labeled
        # a publisher-authenticated DOI just because it mentions the identifier.
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != archived["content_sha256"]:
            raise ValueError("archive data changed during authoring")
        sections.append(ReportSection(
            heading="Archived source " + str(len(sections) + 1),
            body=("Archive SHA256: " + digest + "\nSource URL: " +
                  archived["url"] + "\nUntrusted quotation: " + content),
            cited_dois=(doi,),
        ))
    return author_research_report(
        title=title, sections=tuple(sections), citations=citations)

