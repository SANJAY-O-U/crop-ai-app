"""
Raw ERA5-Land -> tabular long-format schema:

    timestamp, latitude, longitude, variable, value, unit, source

`source` is always "era5_land_reanalysis_proxy" for anything that came
through this pipeline — never "observation". See research/README.md,
section "Why 'reanalysis proxy', never 'observation'".

Every unit conversion is delegated to units.py and every converted value
keeps an explicit `unit` column — nothing is silently left ambiguous.
"""

import warnings

import pandas as pd

from pipeline import units
from pipeline.coordinates import extract_point_timeseries

SOURCE_LABEL = "era5_land_reanalysis_proxy"

TABLE_COLUMNS = ["timestamp", "latitude", "longitude", "variable", "value", "unit", "source"]

RAW_VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "total_precipitation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
]

# Real CDS-delivered ERA5-Land NetCDF files (confirmed 2026-09-21 against an
# actual pilot download, data/raw/era5_land/era5_land_pilot_202306.nc) use
# short CF/GRIB variable names ON DISK, NOT the long names used in the CDS
# *request* (era5_land/acquire.py's VARIABLES list, which RAW_VARIABLES
# above mirrors). This is an explicit, verified mapping - each short name
# was matched against the real file's actual variable list
# (t2m, d2m, tp, u10, v10), never guessed from ECMWF naming conventions in
# the abstract.
ERA5_LAND_SHORT_NAME_TO_CANONICAL = {
    "t2m": "2m_temperature",
    "d2m": "2m_dewpoint_temperature",
    "tp": "total_precipitation",
    "u10": "10m_u_component_of_wind",
    "v10": "10m_v_component_of_wind",
}


def _row(ts, lat, lon, variable, value, unit, source):
    return {
        "timestamp": ts, "latitude": lat, "longitude": lon,
        "variable": variable, "value": value, "unit": unit, "source": source,
    }


def normalize_point_records(
    records: list[dict], latitude: float, longitude: float, source: str = SOURCE_LABEL
) -> pd.DataFrame:
    """
    Convert raw per-timestep records (as produced by
    coordinates.extract_point_timeseries) into the long-format schema,
    applying documented unit conversions.

    IMPORTANT: `total_precipitation` here is assumed to already be the
    hourly (de-accumulated) amount in metres — if the raw series spans a
    full ERA5-Land forecast cycle, run units.deaccumulate_precipitation_m()
    on it BEFORE calling this function. This function does not know about
    forecast-cycle boundaries and cannot de-accumulate correctly on its own.
    """
    rows = []

    for rec in records:
        ts = pd.Timestamp(rec["time"])
        temp_c = dewpoint_c = None

        if "2m_temperature" in rec and rec["2m_temperature"] is not None:
            temp_c = units.kelvin_to_celsius(rec["2m_temperature"])
            rows.append(_row(ts, latitude, longitude, "temperature_c", temp_c, "C", source))

        if "2m_dewpoint_temperature" in rec and rec["2m_dewpoint_temperature"] is not None:
            dewpoint_c = units.kelvin_to_celsius(rec["2m_dewpoint_temperature"])
            rows.append(_row(ts, latitude, longitude, "dewpoint_c", dewpoint_c, "C", source))

        if temp_c is not None and dewpoint_c is not None:
            rh = units.relative_humidity_pct(temp_c, dewpoint_c)
            rows.append(_row(ts, latitude, longitude, "relative_humidity_pct", rh, "%", source))

        if "total_precipitation" in rec and rec["total_precipitation"] is not None:
            mm = units.precipitation_m_to_mm(rec["total_precipitation"])
            rows.append(_row(ts, latitude, longitude, "rainfall_mm", mm, "mm", source))

        u = rec.get("10m_u_component_of_wind")
        v = rec.get("10m_v_component_of_wind")
        if u is not None and v is not None:
            speed = units.wind_components_to_speed_kmph(u, v)
            rows.append(_row(ts, latitude, longitude, "wind_speed_kmph", speed, "km/h", source))

    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def _deaccumulate_precipitation_records(records: list[dict]) -> list[dict]:
    """
    Replace each record's raw (still forecast-cycle-accumulated)
    total_precipitation with its true per-hour amount, using the DOCUMENTED
    ERA5-Land convention (units.deaccumulate_era5_land_precipitation_m —
    see that function's docstring for the exact ECMWF source quote).
    Records with no "total_precipitation" key at all are passed through
    unchanged (e.g. a file that never requested precipitation).

    Any within-cycle anomaly the de-accumulation clamps to 0.0 raises a
    Python warning naming the affected timestamp(s) — never silently
    dropped, per this fix's requirement not to discard anomalies quietly.
    """
    if not records or "total_precipitation" not in records[0]:
        return records

    raw_values = [r.get("total_precipitation") for r in records]
    hours_utc = [pd.Timestamp(r["time"]).hour for r in records]
    hourly_values, anomaly_indices = units.deaccumulate_era5_land_precipitation_m(raw_values, hours_utc)

    for record, hourly_value in zip(records, hourly_values):
        record["total_precipitation"] = hourly_value

    if anomaly_indices:
        bad_times = [str(records[i]["time"]) for i in anomaly_indices]
        warnings.warn(
            f"deaccumulate_era5_land_precipitation_m clamped "
            f"{len(anomaly_indices)} unexpected within-cycle accumulation "
            f"decrease(s) to 0.0 at: {bad_times}",
            stacklevel=2,
        )

    return records


def normalize_era5_land_file(
    path: str, latitude: float, longitude: float, source: str = SOURCE_LABEL
) -> pd.DataFrame:
    """
    End-to-end: open a real ERA5-Land netCDF file, extract the nearest
    gridpoint's time series for the standard variable set, normalize units,
    return the long-format DataFrame. Requires xarray + netCDF4 (a real
    downloaded file) — this is the function run_normalize.py calls.

    Real CDS ERA5-Land files use short on-disk names
    (ERA5_LAND_SHORT_NAME_TO_CANONICAL) and a "valid_time" coordinate
    instead of "time". Both are renamed to this pipeline's existing
    canonical names immediately after opening — before anything else runs —
    so extract_point_timeseries(), RAW_VARIABLES, and
    normalize_point_records() all keep working completely unchanged,
    whether fed a real CDS file or the synthetic test fixture.

    PRECIPITATION: total_precipitation IS de-accumulated here, using the
    documented ERA5-Land convention (once-daily 00 UTC forecast base — see
    units.deaccumulate_era5_land_precipitation_m()'s docstring for the exact
    ECMWF source). The resulting rainfall_mm values are true per-hour
    rainfall, EXCEPT for the very first timestep of the requested window
    (which has no earlier data to de-accumulate against and is left absent
    from the output — see that function's docstring — unless the window
    happens to start exactly on a fresh cycle's hour 01 UTC).
    """
    import xarray as xr

    dataset = xr.open_dataset(path)
    try:
        rename_map = {
            short_name: canonical_name
            for short_name, canonical_name in ERA5_LAND_SHORT_NAME_TO_CANONICAL.items()
            if short_name in dataset.data_vars
        }
        if "valid_time" in dataset.coords and "time" not in dataset.coords:
            rename_map["valid_time"] = "time"
        if rename_map:
            dataset = dataset.rename(rename_map)

        records = extract_point_timeseries(dataset, latitude, longitude, RAW_VARIABLES)
    finally:
        dataset.close()

    records = _deaccumulate_precipitation_records(records)
    return normalize_point_records(records, latitude, longitude, source)
