"""
Typed weather-provider failures.

A provider failure is NEVER represented as weather data. Every failure carries a short machine-readable `kind` so the
service can log it, expose it (as `fallback_reason` or an HTTP error) and keep it distinguishable from legitimate
weather values.

Two classes also inherit from the builtin exceptions they correspond to (ConnectionError / TimeoutError) so callers and
tests that catch the builtin types keep working.
"""

KINDS = ("timeout", "connection", "http_error", "malformed_response", "invalid_payload", "unexpected_units", "empty_forecast")


class ProviderError(Exception):
    """The live weather provider did not return usable data."""

    kind = "provider_error"

    def __init__(self, message: str, kind: str | None = None, upstream_status: int | None = None):
        super().__init__(message)
        if kind:
            self.kind = kind
        self.upstream_status = upstream_status

    @property
    def reason(self) -> str:
        return f"{self.kind}: {self}"[:240]


class ProviderUnavailableError(ProviderError, ConnectionError):
    """Network-level failure (could not connect / connection dropped)."""

    kind = "connection"


class ProviderTimeoutError(ProviderUnavailableError, TimeoutError):
    kind = "timeout"


class ProviderResponseError(ProviderError):
    """The provider answered, but not with a usable forecast (HTTP error, malformed JSON, bad values, ...)."""

    kind = "malformed_response"


class WeatherUnavailableError(ProviderError):
    """Raised by the service when the provider failed AND fallback to mock data is disabled (WEATHER_FALLBACK=error)."""

    kind = "weather_unavailable"

    def __init__(self, cause: ProviderError):
        super().__init__(str(cause), kind=cause.kind, upstream_status=cause.upstream_status)
        self.cause = cause
