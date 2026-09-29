"""Validated plugin registration without coupling plugins to Core internals."""

from aura_core.plugins.registry import PluginManifest, PluginRegistry

__all__ = ["PluginManifest", "PluginRegistry"]
