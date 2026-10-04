from __future__ import annotations

import os
from fastapi.testclient import TestClient

# AURA deterministik mimarisinde Kernel ve Config'in düzgün ayağa kalkması için
# çevre değişkenleri app import edilmeden hemen önce ayarlanmalıdır.
os.environ["AURA_MODEL"] = "qwen3:4b-instruct-2507-q4_K_M"
os.environ["AURA_EVENT_STREAM_TOKEN"] = "test-diagnostics-token-0123456789abcdef"

from aura_core.main import app

def test_diagnostics_is_safe_and_registered(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Gerçek production app objesini with bloğu (lifespan) içinde ayağa kaldırıyoruz
    with TestClient(app) as client:
        response = client.get("/api/diagnostics")

        assert response.status_code == 200, f"Diagnostics failed: {response.text}"

        data = response.json()
        assert "status" in data
        assert "services" in data
        assert "health" in data
