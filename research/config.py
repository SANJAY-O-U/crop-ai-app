"""
Copernicus CDS credential loading.

CREDENTIALS ARE NEVER HARDCODED HERE. Configure them one of two ways:

  Option A  -  environment variables (preferred, works everywhere):
      CDSAPI_URL=https://cds.climate.copernicus.eu/api
      CDSAPI_KEY=<your-personal-access-token>

  Option B  -  the traditional cdsapi config file at $HOME/.cdsapirc:
      url: https://cds.climate.copernicus.eu/api
      key: <your-personal-access-token>

See research/README.md for the exact step-by-step signup process.

Known cdsapi quirk (ecmwf/cdsapi issue #91): the client does not always pick
up CDSAPI_URL/CDSAPI_KEY from the environment automatically, so this module
reads them explicitly and passes them into cdsapi.Client(url=..., key=...)
rather than relying on the client's own env-var detection.
"""

import os
from pathlib import Path

CDSAPI_URL_DEFAULT = "https://cds.climate.copernicus.eu/api"


class MissingCredentialsError(RuntimeError):
    """Raised when no CDS credentials can be found anywhere."""


def _read_cdsapirc() -> dict | None:
    """Best-effort parse of ~/.cdsapirc (simple 'key: value' lines)."""
    rc_path = Path.home() / ".cdsapirc"
    if not rc_path.exists():
        return None

    values = {}
    for line in rc_path.read_text().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()

    if "key" in values:
        return {"url": values.get("url", CDSAPI_URL_DEFAULT), "key": values["key"]}
    return None


def get_cds_credentials() -> dict:
    """
    Resolve CDS credentials from environment variables first, then
    ~/.cdsapirc. Raises MissingCredentialsError with an actionable message
    if neither is present  -  callers must NOT catch this and silently
    proceed with fake data.
    """
    env_key = os.getenv("CDSAPI_KEY")
    if env_key:
        return {"url": os.getenv("CDSAPI_URL", CDSAPI_URL_DEFAULT), "key": env_key}

    from_file = _read_cdsapirc()
    if from_file:
        return from_file

    raise MissingCredentialsError(
        "No Copernicus CDS credentials found.\n"
        "Set the CDSAPI_KEY (and optionally CDSAPI_URL) environment "
        "variables, or create $HOME/.cdsapirc.\n"
        "See research/README.md, section 'Getting CDS credentials', for the "
        "exact signup steps  -  this cannot be done automatically."
    )


def get_cds_client():
    """Return an authenticated cdsapi.Client, or raise MissingCredentialsError."""
    import cdsapi  # imported lazily so this module has no hard dependency at import time

    creds = get_cds_credentials()
    return cdsapi.Client(url=creds["url"], key=creds["key"])
