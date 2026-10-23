"""Build-time, PUBLIC (non-secret) publisher settings for signed updates.

The Windows CI may populate these from GitHub Actions repository VARIABLES,
never from the software user interface or a GitHub artifact URL. If unset,
the built EXE safely disables network update checks.
"""
UPDATE_MANIFEST_URL = ''
UPDATE_PUBLIC_KEY_B64 = ''
