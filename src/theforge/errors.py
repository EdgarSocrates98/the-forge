"""User-facing error types mapped to CLI exit codes."""


class ForgeError(Exception):
    """Base class for expected, user-facing failures."""


class UsageError(ForgeError):
    """Invalid input or workspace state (exit 2)."""


class PersistenceError(ForgeError):
    """A run or cache file could not be written (exit 5)."""
