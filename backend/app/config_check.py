"""
Environment validation for deployment. Reports problems by variable NAME only (values are never echoed).

    python -m app.config_check            # prints JSON; exit 1 if any variable is invalid, or (APP_ENV=production) a
                                          # production requirement is not met

`errors`          a variable has an invalid value (the app would misbehave or ignore it)
`production_gaps` only evaluated when APP_ENV=production: settings that must be in place for a production deployment
"""

import json
import os
import sys

_VALID = {"WEATHER_PROVIDER": {"open-meteo", "mock"}, "WEATHER_FALLBACK": {"mock", "error"}, "DOWNSCALING_METHOD": {"baseline", "ml_corrected"},
          "LOG_LEVEL": {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}}
_NUMERIC = {"WEATHER_CACHE_TTL_S": 0, "WEATHER_FAILURE_COOLDOWN_S": 0, "MAX_UPLOAD_MB": 0.001}


def check_environment(env=None) -> dict:
    env = os.environ if env is None else env
    get = lambda k: (env.get(k) or "").strip()
    errors, gaps = [], []

    for key, allowed in _VALID.items():
        v = get(key)
        if v and (v.upper() if key == "LOG_LEVEL" else v.lower()) not in allowed:
            errors.append(f"{key}: not one of {sorted(allowed)}")
    for key, minimum in _NUMERIC.items():
        v = get(key)
        if v:
            try:
                if float(v) < minimum:
                    raise ValueError
            except ValueError:
                errors.append(f"{key}: must be a number >= {minimum}")
    port = get("PORT")
    if port and not (port.isdigit() and 1 <= int(port) <= 65535):
        errors.append("PORT: must be an integer 1-65535")

    production = get("APP_ENV").lower() == "production"
    if production:
        origins = get("ALLOWED_ORIGINS")
        if not origins or origins == "*":
            gaps.append("ALLOWED_ORIGINS: must list the frontend origin(s), not '*' or empty")
        elif any(not o.strip().startswith(("https://", "http://localhost")) for o in origins.split(",") if o.strip()):
            gaps.append("ALLOWED_ORIGINS: production origins should be https://")
        if get("WEATHER_FALLBACK").lower() != "error":
            gaps.append("WEATHER_FALLBACK: set to 'error' so a provider outage never serves synthetic weather")
        if get("WEATHER_PROVIDER").lower() not in ("", "open-meteo"):
            gaps.append("WEATHER_PROVIDER: must be 'open-meteo' in production")
        if get("DOWNSCALING_METHOD").lower() not in ("", "baseline"):
            gaps.append("DOWNSCALING_METHOD: only 'baseline' is enabled; remove or set to 'baseline'")
        if get("REQUIRE_DISEASE_MODELS").lower() not in ("1", "true", "yes", "on"):
            gaps.append("REQUIRE_DISEASE_MODELS: set to 'true' so the deploy fails if disease models are missing")
    return {"environment": "production" if production else "development", "errors": errors, "production_gaps": gaps,
            "ok": not errors and not gaps}


if __name__ == "__main__":
    result = check_environment()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
