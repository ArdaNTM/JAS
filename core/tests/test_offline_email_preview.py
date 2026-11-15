"""Feature #108: never run HTML or expose attachment contents in MIME preview."""
from __future__ import annotations

from email.message import EmailMessage

import pytest

from aura_core.application.offline_email import preview_eml


def message(*, subject="Research", body="Hello, World!\n"):
    email = EmailMessage()
    email["From"] = "alice@example.org"
    email["To"] = "bob@example.org"
    email["Subject"] = subject
    email.set_content(body)
    return email


def test_plain_text_email_metadata_and_no_execution():
    raw = message().as_bytes()
    view = preview_eml(raw)
    assert view.sender == "alice@example.org"
    assert view.recipients == "bob@example.org"
    assert view.subject == "Research"
    assert "Hello" in view.text_body
    assert len(view.source_sha256) == 64
    assert view.untrusted and not view.authorization_checked
    assert not view.delivery_verified and not view.sent
    assert not view.attachments_opened


def test_multipart_alternative_strips_active_html():
    email = message()
    email.add_alternative(
        "<script>alert('danger')</script><a href='https://evil.invalid/'>link</a>",
        subtype="html",
    )
    view = preview_eml(email.as_bytes())
    assert "Hello" in view.text_body
    assert view.html_omitted
    assert "script" not in view.text_body
    assert "evil.invalid" not in view.text_body


def test_attachment_metadata_only_and_content_not_exposed():
    email = message()
    email.add_attachment(
        b"TOP_SECRET_DATA", maintype="application",
        subtype="octet-stream", filename="notes.bin",
    )
    view = preview_eml(email.as_bytes())
    assert len(view.attachments) == 1
    assert view.attachments[0].filename == "notes.bin"
    assert view.attachments[0].size_bytes == 15
    assert not view.attachments[0].content_exposed
    assert "TOP_SECRET" not in repr(view)
    assert view.text_body.strip() == "Hello, World!"


def test_unicode_subject_and_quoted_printable_body():
    email = message(subject="Türkçe – Merhaba", body="çalışma ve deneme")
    view = preview_eml(email.as_bytes())
    assert view.subject == "Türkçe – Merhaba"
    assert "çalışma" in view.text_body


def test_reject_duplicate_from_headers():
    raw = (b"From: a@example.org\r\nFrom: b@example.org\r\n"
           b"To: x@example.org\r\nSubject: Ambiguous\r\n"
           b"Content-Type: text/plain\r\n\r\nbody")
    with pytest.raises(ValueError, match="duplicate"):
        preview_eml(raw)


def test_non_email_and_oversized_payload_rejected():
    for raw in ("path/to/mail.eml", bytearray(b"From: a"), b"", b"x" * (512 * 1024 + 1)):
        with pytest.raises(ValueError):
            preview_eml(raw)


def test_invalid_part_budget_and_excessive_leaf_parts():
    email = message()
    for i in range(8):
        email.add_attachment(
            b"hello", maintype="application", subtype="octet-stream",
            filename=f"attachment{i}.bin",
        )
    with pytest.raises(ValueError, match="part budget"):
        preview_eml(email.as_bytes(), max_parts=3)
    with pytest.raises(ValueError):
        preview_eml(email.as_bytes(), max_parts=True)


def test_dangerous_attachment_name_refused_even_without_file_io():
    raw = (b"From: a@example.org\r\nTo: b@example.org\r\n"
           b"Subject: Test\r\nMIME-Version: 1.0\r\n"
           b"Content-Type: application/octet-stream\r\n"
           b"Content-Disposition: attachment; filename=\"../passwords\"\r\n\r\n"
           b"anything")
    with pytest.raises(ValueError, match="unsafe attachment"):
        preview_eml(raw)


def test_html_only_content_is_not_interpreted_as_plain_text():
    email = EmailMessage()
    email["From"] = "alice@example.org"
    email["To"] = "bob@example.org"
    email["Subject"] = "HTML only"
    email.set_content("<img src='https://evil.invalid/pixel'>", subtype="html")
    view = preview_eml(email.as_bytes())
    assert view.html_omitted
    assert view.text_body == ""


def test_body_overflow_fails_closed():
    email = message(body="x" * 100001)
    with pytest.raises(ValueError, match="text body exceeds"):
        preview_eml(email.as_bytes())
