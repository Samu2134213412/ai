"""Model provider abstraction.

Claude Code reaches a model through the Anthropic Messages API, so a provider's
job is (a) to say how healthy it is and (b) to produce the environment variables
that point Claude Code at it. Adding Claude API, an OpenAI-compatible gateway,
Agent Factory or another local runtime later means adding a class here — nothing
elsewhere in the codebase names Ollama or qwen3-coder.
"""

from .base import ModelProvider, ProviderHealth
from .ollama import OllamaProvider

#: Registry of implemented providers. Planned-but-unimplemented providers are
#: deliberately absent rather than stubbed out.
PROVIDERS: dict[str, type[ModelProvider]] = {
    OllamaProvider.key: OllamaProvider,
}


def get_provider(settings) -> ModelProvider:
    try:
        cls = PROVIDERS[settings.provider]
    except KeyError:
        raise ValueError(
            f"unknown provider '{settings.provider}'. Available: {sorted(PROVIDERS)}"
        ) from None
    return cls(settings)


__all__ = ["ModelProvider", "ProviderHealth", "OllamaProvider", "PROVIDERS", "get_provider"]
