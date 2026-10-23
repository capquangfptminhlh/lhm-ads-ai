"""Single source of truth for the LHM Ads AI product version.

Every machine-readable consumer (FastAPI app metadata, the /healthz status
endpoint, release tooling) must import ``__version__`` from here instead of
hardcoding a string. Human-facing documents (README.md, docs/STUDIO.md)
display the short form "0.3" for the current release; the canonical value
below is its full semantic version, "0.3.1".

Bump this value — and only this value — when cutting a new release, and
record the change in CHANGELOG.md.
"""

__version__ = "0.3.1"

__all__ = ["__version__"]
