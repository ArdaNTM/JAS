"""Bounded, principal-scoped, ephemeral conversation review.

Input turns must already be authenticated and authorized by a caller using
the existing Kernel/PermissionEngine/MCP Gateway. This module never saves,
forgets, executes, or promotes a memory; candidates are untrusted proposals.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_PREFIXES = ("remember:", "hatırla:")
_MAX_TURN_BYTES = 4096
_MAX_SEEN_IDS = 2048


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    turn_id: str
    speaker: str
    content: str
    speaker_identity_verified: bool = False
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    source_turn_id: str
    proposed_text: str
    untrusted: bool = True
    owner_approval_verified: bool = False
    persisted: bool = False


@dataclass(frozen=True, slots=True)
class ConversationView:
    turns: tuple[ConversationTurn, ...]
    principal_fingerprint: str
    conversation_fingerprint: str
    retained_count: int
    untrusted: bool = True
    authorization_checked: bool = False
    persisted: bool = False


def _identity(value: str, label: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


class OfflineConversationReview:
    """A single bounded in-memory transcript, not a persistent conversation log."""

    def __init__(
        self, *, principal_id: str, conversation_id: str,
        max_turns: int = 80, max_chars: int = 12000,
    ) -> None:
        self._principal = _identity(principal_id, "principal")
        self._conversation = _identity(conversation_id, "conversation")
        if type(max_turns) is not int or not 1 <= max_turns <= 128:
            raise ValueError("max_turns must be 1..128")
        if type(max_chars) is not int or not 128 <= max_chars <= 20000:
            raise ValueError("max_chars must be 128..20000")
        self.max_turns = max_turns
        self.max_chars = max_chars
        self._seen: set[str] = set()
        self._turns: list[ConversationTurn] = []
        self._chars = 0

    def _scope(self, *, principal_id: str, conversation_id: str) -> None:
        principal = _identity(principal_id, "principal")
        conversation = _identity(conversation_id, "conversation")
        if principal != self._principal or conversation != self._conversation:
            raise PermissionError("conversation scope mismatch")

    def append(
        self, *, principal_id: str, conversation_id: str,
        turn_id: str, speaker: str, content: str,
    ) -> ConversationTurn:
        """Append data, but never authenticate a speaker or store a memory."""
        self._scope(principal_id=principal_id, conversation_id=conversation_id)
        turn = _identity(turn_id, "turn")
        if type(speaker) is not str or speaker not in {"user", "assistant"}:
            raise ValueError("speaker must be user or assistant")
        if (
            type(content) is not str or not content.strip()
            or "\x00" in content or "\r" in content
            or len(content) > self.max_chars
        ):
            raise ValueError("invalid or unbounded conversation content")
        try:
            encoded = content.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid conversation Unicode") from exc
        if len(encoded) > _MAX_TURN_BYTES:
            raise ValueError("turn UTF-8 byte budget exceeded")
        if turn in self._seen:
            raise ValueError("duplicate conversation turn")
        if len(self._seen) >= _MAX_SEEN_IDS:
            raise ValueError("conversation replay ledger exhausted")
        record = ConversationTurn(turn, speaker, content)
        self._seen.add(turn)
        self._turns.append(record)
        self._chars += len(content)
        while len(self._turns) > self.max_turns or self._chars > self.max_chars:
            evicted = self._turns.pop(0)
            self._chars -= len(evicted.content)
        return record

    def history(
        self, *, principal_id: str, conversation_id: str,
        limit: int = 20,
    ) -> ConversationView:
        self._scope(principal_id=principal_id, conversation_id=conversation_id)
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid history limit")
        # The public default must work even for smaller configured buffers;
        # requesting extra history never bypasses the configured retention cap.
        turns = tuple(self._turns[-min(limit, self.max_turns):])
        return ConversationView(
            turns=turns,
            principal_fingerprint=hashlib.sha256(
                self._principal.encode("utf-8")
            ).hexdigest(),
            conversation_fingerprint=hashlib.sha256(
                self._conversation.encode("utf-8")
            ).hexdigest(),
            retained_count=len(self._turns),
        )

    def propose_explicit_memories(
        self, *, principal_id: str, conversation_id: str,
        user_requested_review: bool = False,
        max_candidates: int = 10,
    ) -> tuple[MemoryProposal, ...]:
        """Review explicit first-person commands; never auto-persist proposals.

        The flag is only a local opt-in to review. It is NOT an Owner receipt.
        The caller must independently verify that each 'user' turn is authentic.
        """
        self._scope(principal_id=principal_id, conversation_id=conversation_id)
        if type(user_requested_review) is not bool:
            raise ValueError("explicit review flag must be boolean")
        if type(max_candidates) is not int or not 1 <= max_candidates <= 20:
            raise ValueError("max_candidates must be 1..20")
        if not user_requested_review:
            return ()
        proposals: list[MemoryProposal] = []
        for turn in reversed(self._turns):
            if turn.speaker != "user":
                continue
            text = turn.content.strip()
            lower = text.casefold()
            for prefix in _PREFIXES:
                if lower.startswith(prefix):
                    proposed = text[len(prefix):].strip()
                    if (
                        not proposed or len(proposed) > 500
                        or any(ord(char) < 32 for char in proposed)
                    ):
                        break
                    proposals.append(MemoryProposal(turn.turn_id, proposed))
                    break
            if len(proposals) >= max_candidates:
                break
        return tuple(reversed(proposals))

    def clear(
        self, *, principal_id: str, conversation_id: str,
        confirm: bool = False,
    ) -> int:
        """Erase this instance's volatile turns; not persistent memory or backups."""
        self._scope(principal_id=principal_id, conversation_id=conversation_id)
        if type(confirm) is not bool or not confirm:
            raise PermissionError("explicit volatile conversation erasure required")
        removed = len(self._turns)
        self._turns.clear()
        self._seen.clear()
        self._chars = 0
        return removed
