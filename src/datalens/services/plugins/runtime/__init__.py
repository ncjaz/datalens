"""
Plugin runtime (application layer).

This subpackage contains the runtime-facing contracts and orchestration for
enabled plugins:

- `contracts`: public plugin hook interfaces + contexts
- `host`: the `PluginHost` coordinator (enable/disable + lifecycle)
- `loader`: safe module loading for shipped + user plugins
- `dispatcher`: hook call policy (logging + best-effort error handling)
"""

from datalens.services.plugins.runtime.contracts import (
    BasePlugin,
    GetPluginFn,
    NoopPlugin,
    PluginAppContext,
    PluginFutureResult,
    PluginProjectContext,
    ProjectAwarePlugin,
)

__all__ = [
    "BasePlugin",
    "GetPluginFn",
    "NoopPlugin",
    "PluginAppContext",
    "PluginFutureResult",
    "PluginProjectContext",
    "ProjectAwarePlugin",
]

