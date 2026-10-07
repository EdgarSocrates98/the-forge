"""Provider registry: sources, describe/refresh, cache, trust and health."""

from theforge.registry.config import (
    ProviderEntry,
    builtin_entries,
    load_entries,
    resolve_entries,
    user_cache_dir,
    user_config_dir,
)
from theforge.registry.health import HealthOutcome, check_health
from theforge.registry.identity import ProviderFingerprint, fingerprint
from theforge.registry.registry import Registry, RegistryRecord, RevalidationOutcome
from theforge.registry.remote import (
    FetchResponse,
    HttpRegistrySource,
    network_disabled,
)
from theforge.registry.sources import (
    FileRegistrySource,
    SourceRead,
    SourceSpec,
    load_source_specs,
    local_document,
    read_sources,
)
from theforge.registry.surface import (
    capability_fingerprint,
    surface_fingerprint,
    surface_identity,
)

__all__ = [
    "FetchResponse", "FileRegistrySource", "HealthOutcome", "HttpRegistrySource",
    "ProviderEntry", "ProviderFingerprint", "Registry", "RegistryRecord",
    "RevalidationOutcome", "SourceRead", "SourceSpec",
    "builtin_entries", "capability_fingerprint", "check_health", "fingerprint",
    "load_entries", "load_source_specs", "local_document", "network_disabled",
    "read_sources", "resolve_entries", "surface_fingerprint", "surface_identity",
    "user_cache_dir", "user_config_dir",
]
