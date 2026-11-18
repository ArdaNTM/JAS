import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from aura_core.application.hud_game_blueprint import generate_local_game, verify_local_game
from aura_core.application.hud_api import HUDPanelRequest, get_game_project


def request(peer="127.0.0.1", host="localhost:8000"):
    return Request({"type":"http","method":"GET","path":"/api/hud/game/project",
                    "headers":[(b"host",host.encode())],"client":(peer,4321),
                    "server":("127.0.0.1",8000),"scheme":"http"})


def test_seeded_game_generation_is_reproducible():
    a=generate_local_game(31415,6)
    b=generate_local_game(31415,6)
    assert a==b and verify_local_game(a)
    assert a.digest==b.digest and len(a.targets)==6
    assert len({t.object_id for t in a.targets})==6


def test_game_geometry_is_bounded_and_serializable():
    a=generate_local_game(98765,24)
    data=a.as_json()
    assert data["version"]==1 and len(data["digest"])==64
    assert all(-4 <= t.x <= 4 and 0.1 < t.radius <= 0.5 and -3 <= t.z <= 3 for t in a.targets)
    assert all(t["shape"]=="sphere" for t in data["targets"])


@pytest.mark.parametrize("seed,count",[
    (0,6),(-1,6),(2**31,6),(1,0),(1,25),(True,6),(1,False),(3.14,6),
])
def test_rejects_invalid_project_parameters(seed,count):
    with pytest.raises(ValueError):
        generate_local_game(seed,count)


def test_game_integrity_detects_mutation():
    a=generate_local_game(31415)
    from dataclasses import replace
    with pytest.raises(TypeError):
        a.targets[0].radius=999
    assert not verify_local_game(replace(a,digest="0"*64))


def test_hud_panel_schema_is_view_only_and_closed_set():
    assert HUDPanelRequest(title="Hologram", kind="hologram").kind=="hologram"
    assert HUDPanelRequest(title="Local Game", kind="game").kind=="game"
    for invalid in ("shell","physical_action","screen_read","<script>"):
        with pytest.raises(ValidationError):
            HUDPanelRequest(title="AURA",kind=invalid)


def test_http_game_endpoint_is_local_only_and_deterministic():
    result=asyncio.run(get_game_project(request(),seed=123,target_count=4,principal_id="owner"))
    assert result==generate_local_game(123,4).as_json()
    assert result["seed"]==123


def test_http_game_endpoint_rejects_remote_peer():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_game_project(request(peer="192.0.2.1"),seed=123,
                                     target_count=4,principal_id="owner"))
    assert exc.value.status_code==403


def test_http_game_endpoint_rejects_external_host():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_game_project(request(host="evil.example"),seed=123,
                                     target_count=4,principal_id="owner"))
    assert exc.value.status_code==403
