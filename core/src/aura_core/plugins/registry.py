"""Plugin manifests are explicit capability and permission declarations."""

from dataclasses import dataclass, field
from enum import StrEnum


class PluginState(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    version: str
    capabilities: frozenset[str]
    required_permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.plugin_id or not self.version:
            raise ValueError("Plugin id and version are required")


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, tuple[PluginManifest, PluginState]] = {}

    def register(self, manifest: PluginManifest) -> None:
        if manifest.plugin_id in self._plugins:
            raise ValueError(f"Plugin already registered: {manifest.plugin_id}")
        self._plugins[manifest.plugin_id] = manifest, PluginState.REGISTERED

    def activate(self, plugin_id: str) -> None:
        manifest, state = self._plugins[plugin_id]
        if state is PluginState.RETIRED:
            raise LookupError(f"Plugin is retired: {plugin_id}")
        self._plugins[plugin_id] = manifest, PluginState.ACTIVE

    def manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(self._plugins[key][0] for key in sorted(self._plugins))
