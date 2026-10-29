"""Provider modules. Each one is independent and implements `base.Provider`."""

from .antigravity import AntigravityProvider
from .claude import ClaudeProvider
from .codex import CodexProvider

ALL = (ClaudeProvider, CodexProvider, AntigravityProvider)
