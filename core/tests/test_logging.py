import json
import logging

from aura_core.observability.logging import JsonFormatter


def test_json_formatter_serializes_operational_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="aura_core.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP request completed",
        args=(),
        exc_info=None,
    )
    record.event = "http_request_completed"
    record.method = "GET"
    record.path = "/ready"
    record.status_code = 200
    record.latency_ms = 1.25
    record.request_id = "request-123"

    payload = json.loads(formatter.format(record))

    assert payload["timestamp"].endswith("+00:00")
    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "logger": "aura_core.http",
        "message": "HTTP request completed",
        "event": "http_request_completed",
        "method": "GET",
        "path": "/ready",
        "status_code": 200,
        "latency_ms": 1.25,
        "request_id": "request-123",
    }
