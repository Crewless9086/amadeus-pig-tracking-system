"""Canonical CHARLIE/CORE environment resolution with fail-closed aliases."""

from __future__ import annotations

import os
from collections.abc import Mapping


class EnvironmentConflictError(RuntimeError):
    """Raised without values when canonical and legacy configuration disagree."""


ALIASES = {
    "CHARLIE_EXECUTIVE_ENABLED": ("CHARLIE_PRIVATE_EXECUTIVE_ENABLED",),
    "CHARLIE_LLM_ENABLED": ("CHARLIE_PRIVATE_LLM_ENABLED",),
    "CHARLIE_LLM_MODEL": ("CHARLIE_PRIVATE_LLM_MODEL",),
    "CHARLIE_LLM_URL": ("CHARLIE_PRIVATE_LLM_URL",),
    "CHARLIE_TELEGRAM_BOT_TOKEN": ("CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN",),
    "CHARLIE_TELEGRAM_WEBHOOK_SECRET": ("CHARLIE_PRIVATE_TELEGRAM_WEBHOOK_SECRET",),
    "CHARLIE_TELEGRAM_OWNER_USER_ID": ("CHARLIE_PRIVATE_TELEGRAM_OWNER_USER_ID",),
    "CHARLIE_TELEGRAM_OWNER_CHAT_ID": ("CHARLIE_PRIVATE_TELEGRAM_OWNER_CHAT_ID",),
    "CHARLIE_TRANSCRIPTION_ENABLED": ("CHARLIE_PRIVATE_TRANSCRIPTION_ENABLED",),
    "CHARLIE_TRANSCRIPTION_MODEL": ("CHARLIE_PRIVATE_TRANSCRIPTION_MODEL",),
    "CHARLIE_TTS_ENABLED": ("CHARLIE_PRIVATE_TTS_ENABLED",),
    "CHARLIE_TTS_PROVIDER": ("CHARLIE_PRIVATE_TTS_PROVIDER",),
    "CHARLIE_TTS_MODEL": ("CHARLIE_PRIVATE_TTS_MODEL",),
    "CHARLIE_TTS_VOICE_ID": ("CHARLIE_PRIVATE_TTS_VOICE_ID",),
    "CORE_NOTIFICATION_MODE": ("CHARLIE_CORE_NOTIFICATION_MODE",),
    "CORE_EXECUTION_BASE_BRANCH": ("CHARLIE_RUNNER_BASE_BRANCH",),
    "CORE_RUNNER_LEASE_TTL_SECONDS": ("CHARLIE_RUNNER_LEASE_TTL_SECONDS",),
    "CORE_EXECUTION_ROOT": ("CHARLIE_EXECUTION_ROOT",),
    "CORE_RELEASE_VERIFY_URL": ("CHARLIE_RELEASE_VERIFY_URL",),
    "CORE_LOCAL_PREVIEW_URL": ("CHARLIE_LOCAL_PREVIEW_URL",),
    "CORE_REQUIRE_AGENT_MODEL_ROUTING": ("CHARLIE_REQUIRE_AGENT_MODEL_ROUTING",),
    "CORE_REQUIRE_BROWSER_PREFLIGHT": ("CHARLIE_REQUIRE_BROWSER_PREFLIGHT",),
    "CORE_PARALLEL_READONLY_DISABLED": ("CHARLIE_PARALLEL_READONLY_DISABLED",),
    "CORE_PARALLEL_READONLY_WORKERS": ("CHARLIE_PARALLEL_READONLY_WORKERS",),
    "CORE_CLAUDE_MODEL": ("CHARLIE_CLAUDE_MODEL",),
    "CORE_CLAUDE_REVIEW_ENABLED": ("CHARLIE_CLAUDE_REVIEW_ENABLED",),
    "CORE_ANTHROPIC_MAX_TOKENS": ("CHARLIE_ANTHROPIC_MAX_TOKENS",),
    "CORE_RELAY_ENABLED": ("CHARLIE_BUILD_RELAY_ENABLED",),
    "CORE_RELAY_BOT_TOKEN": ("CHARLIE_BUILD_RELAY_BOT_TOKEN",),
    "CORE_RELAY_WEBHOOK_SECRET": ("CHARLIE_BUILD_RELAY_WEBHOOK_SECRET",),
    "CORE_RELAY_ALLOWED_USER_IDS": ("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS",),
    "CORE_RELAY_CODEX_CHAT_WRITE_ENABLED": ("CHARLIE_BUILD_RELAY_CODEX_CHAT_WRITE_ENABLED",),
    "CORE_RELAY_MISSION_STORE_ENABLED": ("CHARLIE_BUILD_RELAY_MISSION_STORE_ENABLED",),
    "CORE_RELAY_REPO_ROOT": ("CHARLIE_BUILD_RELAY_REPO_ROOT",),
    "CORE_RELAY_BASE_URL": ("CHARLIE_BUILD_RELAY_BASE_URL",),
    "CORE_RELAY_TRANSPORT": ("CHARLIE_TELEGRAM_TRANSPORT",),
    "CHARLIE_TELEGRAM_INGRESS_TRANSPORT": ("CHARLIE_TELEGRAM_TRANSPORT",),
}


def env_value(canonical, default="", *, environ=None, aliases=None):
    source = os.environ if environ is None else environ
    legacy_names = tuple(ALIASES.get(canonical, ())) if aliases is None else tuple(aliases)
    present = [(name, str(source.get(name))) for name in (canonical, *legacy_names) if source.get(name) is not None]
    if not present:
        return default
    normalized = {value.strip() for _name, value in present}
    if len(normalized) > 1:
        names = ", ".join(name for name, _value in present)
        raise EnvironmentConflictError(f"environment_alias_conflict:{canonical}:{names}")
    canonical_value = source.get(canonical)
    return canonical_value if canonical_value is not None else present[0][1]


def env_truthy(canonical, default=False, *, environ=None, aliases=None):
    fallback = "1" if default else "0"
    return str(env_value(canonical, fallback, environ=environ, aliases=aliases) or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


class AliasEnvironment(Mapping):
    def __init__(self, source=None):
        self.source = os.environ if source is None else source

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __iter__(self):
        virtual = {
            canonical for canonical, legacy_names in ALIASES.items()
            if canonical in self.source or any(name in self.source for name in legacy_names)
        }
        return iter(set(self.source) | virtual)

    def __len__(self):
        return sum(1 for _key in self)

    def get(self, key, default=None):
        if key in ALIASES:
            return env_value(key, default, environ=self.source)
        return self.source.get(key, default)


def alias_environment(source=None):
    return AliasEnvironment(source)


def core_agent_env_value(kind, key, default="", *, environ=None):
    kind = str(kind).strip().upper()
    key = str(key).strip().upper()
    canonical = f"CORE_{kind}_{key}"
    legacy = f"CHARLIE_{kind}_{key}"
    return env_value(canonical, default, environ=environ, aliases=(legacy,))
