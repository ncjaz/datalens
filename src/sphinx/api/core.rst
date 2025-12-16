Core
====

V2 core modules are still being carved out. As the implementations land, they
should live under `datalens.core` and be documented here.

Core responsibilities:

- Application context wiring (service/container lifetimes)
- Event hub contracts
- Settings schema and validation
- Centralised logging (async + attributed)

.. autosummary::
   :toctree: generated/core
   :recursive:

   datalens.core.app_settings
   datalens.core.context
   datalens.core.events
   datalens.core.logging
