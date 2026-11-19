"""Positive, tampering, privilege-scope and regression cases for #107."""
from dataclasses import replace

import pytest

from aura_core.enterprise.audit_checkpoint import (
    AuditCheckpoint,
    create_audit_checkpoint,
    verify_audit_checkpoint,
    verify_audit_records,
)
from aura_core.enterprise.runtime_controls import HashChainAuditLedger

_KEY = bytes(range(32))
_OTHER_KEY = bytes(range(1, 33))


def _record(ledger: HashChainAuditLedger, principal: str = "owner") -> None:
    ledger.append(
        principal_id=principal, action="data.read", resource_scope="local",
        outcome="denied", reason_code="policy_denied",
    )


def test_checkpoint_authenticates_existing_chain_without_saving_sensitive_metadata():
    ledger = HashChainAuditLedger()
    _record(ledger, "principal-sensitive")
    _record(ledger)
    checkpoint = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")
    assert checkpoint.sequence == 2
    assert verify_audit_records(ledger.snapshot())
    assert verify_audit_checkpoint(ledger, checkpoint, key=_KEY, scope="local-instance")
    assert "principal-sensitive" not in str(checkpoint.to_dict())
    assert "data.read" not in str(checkpoint.to_dict())
    assert set(checkpoint.to_dict()) == {
        "schema", "sequence", "tail_hash", "scope_digest", "previous_mac", "mac",
    }


def test_wrong_key_or_scope_and_tampered_mac_fail_closed():
    ledger = HashChainAuditLedger()
    _record(ledger)
    checkpoint = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")
    assert not verify_audit_checkpoint(ledger, checkpoint, key=_OTHER_KEY, scope="local-instance")
    assert not verify_audit_checkpoint(ledger, checkpoint, key=_KEY, scope="another-instance")
    assert not verify_audit_checkpoint(ledger, replace(checkpoint, mac="f" * 64), key=_KEY, scope="local-instance")
    assert not verify_audit_checkpoint(ledger, replace(checkpoint, sequence=True), key=_KEY, scope="local-instance")
    assert not verify_audit_checkpoint(ledger, replace(checkpoint, tail_hash="x" * 64), key=_KEY, scope="local-instance")


def test_rewrite_and_truncation_are_detected_with_external_checkpoint():
    ledger = HashChainAuditLedger()
    _record(ledger)
    prior = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")
    _record(ledger)
    assert not verify_audit_checkpoint(ledger, prior, key=_KEY, scope="local-instance")
    current = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance", previous=prior)
    assert verify_audit_checkpoint(ledger, current, key=_KEY, scope="local-instance", previous=prior)
    ledger._records.pop()
    assert not verify_audit_checkpoint(ledger, current, key=_KEY, scope="local-instance", previous=prior)
    with pytest.raises(ValueError, match="truncated"):
        create_audit_checkpoint(HashChainAuditLedger(), key=_KEY, scope="local-instance", previous=prior)


def test_rehashed_ledger_cannot_rewrite_an_externally_anchored_history():
    original = HashChainAuditLedger()
    _record(original)
    anchor = create_audit_checkpoint(original, key=_KEY, scope="local-instance")
    alternative = HashChainAuditLedger()
    _record(alternative, "attacker")
    assert alternative.verify()
    with pytest.raises(ValueError, match="rewritten"):
        create_audit_checkpoint(alternative, key=_KEY, scope="local-instance", previous=anchor)
    assert not verify_audit_checkpoint(alternative, anchor, key=_KEY, scope="local-instance")


def test_record_mutations_are_rejected_even_if_in_process_ledger_is_modified():
    ledger = HashChainAuditLedger()
    _record(ledger)
    anchor = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")
    record = ledger.snapshot()[0]
    ledger._records[0] = replace(record, outcome="allowed")
    assert not verify_audit_records(ledger.snapshot())
    assert not verify_audit_checkpoint(ledger, anchor, key=_KEY, scope="local-instance")
    with pytest.raises(ValueError, match="invalid"):
        create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")


def test_invalid_key_scope_and_ledger_are_not_accepted():
    ledger = HashChainAuditLedger()
    for bad_key in (b"short", "not-bytes", b"", None):
        with pytest.raises(ValueError, match="key"):
            create_audit_checkpoint(ledger, key=bad_key, scope="local-instance")
    for bad_scope in ("", "bad\nline", " trailing ", "x" * 257, None):
        with pytest.raises(ValueError, match="scope"):
            create_audit_checkpoint(ledger, key=_KEY, scope=bad_scope)
    with pytest.raises(TypeError, match="ledger"):
        create_audit_checkpoint(object(), key=_KEY, scope="local-instance")
    assert not verify_audit_checkpoint(object(), AuditCheckpoint("x", 0, "0" * 64, "0" * 64, "0" * 64, "0" * 64), key=_KEY, scope="local-instance")


def test_empty_snapshot_is_explicit_not_a_proof_of_executed_actions():
    ledger = HashChainAuditLedger()
    checkpoint = create_audit_checkpoint(ledger, key=_KEY, scope="local-instance")
    assert checkpoint.sequence == 0
    assert checkpoint.tail_hash == "0" * 64
    assert verify_audit_checkpoint(ledger, checkpoint, key=_KEY, scope="local-instance")
