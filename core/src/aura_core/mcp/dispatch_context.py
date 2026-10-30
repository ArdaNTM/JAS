"""Short-lived proof that a provider call is inside authorized Gateway dispatch."""
from contextvars import ContextVar
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DispatchGrant:
    principal_id: str
    capability_id: str
    tool_name: str
    approval_consumed: bool
    risk_level: str

_current = ContextVar("aura_gateway_dispatch", default=None)
def current_dispatch():
    return _current.get()
def enter_dispatch(grant):
    return _current.set(grant)
def leave_dispatch(token):
    _current.reset(token)
