"""Optional MCP surface for The Forge.

The MCP SDK is intentionally an optional dependency. Importing the core
package and using the normal CLI never requires the SDK; ``theforge mcp serve``
reports the installation hint only when the MCP extra is actually requested.
"""

__all__ = ["server"]
