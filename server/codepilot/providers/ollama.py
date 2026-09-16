from __future__ import annotations

from .. import detect
from .base import ModelProvider, ProviderHealth


class OllamaProvider(ModelProvider):
    """Ollama's native Anthropic-compatible endpoint (v0.14.0+).

    Documented contract (docs/api/anthropic-compatibility.mdx in ollama/ollama):

        ANTHROPIC_BASE_URL=http://127.0.0.1:11434
        ANTHROPIC_AUTH_TOKEN=ollama      # required by the client, ignored by Ollama

    Claude Code appends ``/v1/messages`` itself, so the base URL carries no path.
    Claude Code also resolves its model *aliases* through the
    ``ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`` variables; all three are
    pointed at the configured local model so that whichever alias a session or
    subagent asks for, the local model answers.
    """

    key = "ollama"
    label = "Ollama (local)"

    def upstream_url(self) -> str:
        return self.settings.ollama_url.rstrip("/")

    async def health(self) -> ProviderHealth:
        status = await detect.detect_ollama(self.upstream_url())
        model = detect.model_status(status, self.settings.ollama_model)
        return ProviderHealth(
            online=status.available,
            model_available=model.available,
            model=self.settings.ollama_model,
            detail=model.detail or status.detail,
            remedy=model.remedy or status.remedy,
            installed_models=status.extra.get("models", []),
            version=status.version,
        )

    async def list_models(self) -> list[str]:
        status = await detect.detect_ollama(self.upstream_url())
        return status.extra.get("models", [])

    def claude_env(self, base_url_override: str | None = None) -> dict[str, str]:
        model = self.settings.ollama_model
        base_url = (base_url_override or self.upstream_url()).rstrip("/")
        # When the compat proxy is in front, it validates this token; when talking
        # to Ollama directly the token is required by Claude Code but ignored.
        token = self.settings.llm_token if base_url_override else "ollama"
        return {
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_AUTH_TOKEN": token,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            # Ollama reads the context window from its own server process; this is
            # passed through for setups that launch Ollama from the same shell.
            "OLLAMA_CONTEXT_LENGTH": str(self.settings.context_length),
            # An empty API key keeps Claude Code from falling back to a stored
            # Anthropic credential and silently billing the cloud model.
            "ANTHROPIC_API_KEY": "",
        }

    def install_hint(self, model: str) -> str:
        return f"ollama pull {model}"
