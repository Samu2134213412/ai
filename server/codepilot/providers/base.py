from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class ProviderHealth:
    online: bool
    model_available: bool
    model: str
    detail: str | None = None
    remedy: str | None = None
    installed_models: list[str] = field(default_factory=list)
    version: str | None = None


class ModelProvider(abc.ABC):
    """A backend that can serve Claude Code over the Anthropic Messages API."""

    #: Stable identifier stored in settings.provider
    key: str = "abstract"
    #: Human label for the UI
    label: str = "Abstract provider"

    def __init__(self, settings):
        self.settings = settings

    @abc.abstractmethod
    async def health(self) -> ProviderHealth:
        """Live status. Must never start a model download."""

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        """Models this provider can serve right now, without downloading."""

    @abc.abstractmethod
    def claude_env(self, base_url_override: str | None = None) -> dict[str, str]:
        """Environment variables that make Claude Code talk to this provider.

        ``base_url_override`` lets the server insert its compatibility proxy in
        front of the real endpoint.
        """

    @abc.abstractmethod
    def upstream_url(self) -> str:
        """The provider's own Anthropic-compatible base URL."""

    def install_hint(self, model: str) -> str | None:
        """Exact command the user should run to obtain ``model``."""
        return None
