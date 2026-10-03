"""
Deterministic schema of the prospective Open-Meteo forecast archive (RESEARCH ONLY).

Layout (root = data/raw/open_meteo_forecast_archive/, gitignored like all raw data):

    raw/<location_id>/<YYYYMMDD>/<retrieved_utc>_<sha12>.json   exact response bytes, written once, read-only
    index.jsonl     one line per SUCCESSFUL retrieval (IndexRecord)
    errors.jsonl    one line per FAILED attempt (ErrorRecord); a failure never creates a forecast record

Derived (re-creatable from raw, never edited by hand):

    data/processed/forecast_archive/block_forecast_daily.csv   one row per (retrieval, target day) -- see flatten.py
"""

ARCHIVE_VERSION = 1
PROVIDER = "open-meteo"                 # the ONLY provider ever written; mock data is never archived
ROLE_BLOCK_INPUT = "block_input"        # the forecast the live product receives for a block
FORECAST_DAYS = 16                      # Open-Meteo maximum, so every lead 0..15 is preserved
DEFAULT_SLOT_HOURS = 12                 # at most one record per location per 12-h UTC slot

INDEX_FIELDS = [
    "archive_version", "record_id", "location_id", "location_set", "role", "provider", "is_mock",
    "retrieved_utc", "slot_start_utc", "request_url", "request_params", "http_status",
    "raw_path", "raw_sha256", "raw_bytes", "response_meta",
]
RESPONSE_META_FIELDS = ["latitude", "longitude", "elevation", "timezone", "timezone_abbreviation",
                        "utc_offset_seconds", "generationtime_ms", "daily_units", "n_days"]
ERROR_FIELDS = ["archive_version", "location_id", "location_set", "retrieved_utc", "slot_start_utc", "kind",
                "http_status", "message", "body_sha256", "request_url", "request_params"]
ERROR_KINDS = ["http_error", "timeout", "network_error", "invalid_response"]

# Provider daily variable -> normalised name used by the production API (backend/app/weather/schemas.py)
DAILY_FIELD_MAP = {
    "temperature_2m_min": "temperature_min_c",
    "temperature_2m_max": "temperature_max_c",
    "precipitation_sum": "rainfall_mm",
    "relative_humidity_2m_mean": "humidity_pct",
    "windspeed_10m_max": "wind_kmph",
}

# Columns of the derived daily table
DAILY_TABLE_FIELDS = [
    "record_id", "location_id", "location_set", "role", "provider", "is_mock", "retrieved_utc",
    "retrieval_local_date", "retrieval_local_hour", "utc_offset_seconds", "timezone",
    "target_local_date", "lead_days", "response_latitude", "response_longitude", "response_elevation_m",
    "raw_sha256", "raw_path", "any_value_missing",
] + list(DAILY_FIELD_MAP.values())
