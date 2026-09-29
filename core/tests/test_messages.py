import pytest
from pydantic import ValidationError

from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
    Message,
)


MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def test_message_accepts_valid_values() -> None:
    message = Message(
        role="user",
        content="hello",
    )

    assert message.role == "user"
    assert message.content == "hello"


def test_message_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        Message(
            role="user",
            content="",
        )


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        Message(
            role="invalid",
            content="hello",
        )


def test_message_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Message(
            role="user",
            content="hello",
            unexpected="value",
        )


def test_inference_request_accepts_valid_values() -> None:
    request = InferenceRequest(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "hello",
            }
        ],
        temperature=0.0,
        max_tokens=32,
    )

    assert request.model == MODEL
    assert len(request.messages) == 1
    assert request.temperature == 0.0
    assert request.max_tokens == 32


def test_inference_request_defaults() -> None:
    request = InferenceRequest(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "hello",
            }
        ],
    )

    assert request.temperature == 0.7
    assert request.max_tokens is None


def test_inference_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model=MODEL,
            messages=[],
        )


def test_inference_request_rejects_empty_model() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model="",
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
        )


def test_inference_request_rejects_temperature_below_zero() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            temperature=-0.1,
        )


def test_inference_request_rejects_temperature_above_two() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            temperature=2.1,
        )


def test_inference_request_rejects_invalid_max_tokens() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            max_tokens=0,
        )


def test_inference_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            unexpected="value",
        )


def test_inference_response_accepts_valid_values() -> None:
    response = InferenceResponse(
        model=MODEL,
        content="AURA CONTRACT PASS",
        finish_reason="stop",
    )

    assert response.model == MODEL
    assert response.content == "AURA CONTRACT PASS"
    assert response.finish_reason == "stop"


def test_inference_response_allows_missing_finish_reason() -> None:
    response = InferenceResponse(
        model=MODEL,
        content="partial",
    )

    assert response.finish_reason is None


def test_inference_response_rejects_empty_model() -> None:
    with pytest.raises(ValidationError):
        InferenceResponse(
            model="",
            content="response",
        )


def test_inference_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        InferenceResponse(
            model=MODEL,
            content="response",
            unexpected="value",
        )