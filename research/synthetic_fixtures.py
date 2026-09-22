"""
SYNTHETIC test fixture — NOT real ERA5-Land data. Used only to prove the
pipeline code (unit conversion, coordinate extraction, normalization) is
correct, independent of whether real Copernicus credentials are configured.
Values are hand-picked round numbers, not sourced from any dataset.
"""

import numpy as np
import xarray as xr


def make_synthetic_era5_dataset() -> xr.Dataset:
    """
    A tiny 2x2 lat/lon grid, 3 hourly timesteps, with the 5 raw ERA5-Land
    variables this pipeline uses. Grid spacing (0.1 deg) matches ERA5-Land's
    real resolution so nearest-gridpoint tests are realistic in shape, even
    though the values themselves are synthetic.
    """
    latitudes = np.array([13.5, 13.4])
    longitudes = np.array([77.7, 77.8])
    times = np.array(["2023-06-01T00:00", "2023-06-01T01:00", "2023-06-01T02:00"],
                      dtype="datetime64[ns]")

    shape = (len(times), len(latitudes), len(longitudes))

    # 2m_temperature in Kelvin: ~300K (27C) with small variation
    temp_k = np.full(shape, 300.0)
    temp_k[1] += 0.5
    temp_k[2] += 1.0

    # 2m_dewpoint_temperature in Kelvin: a few degrees below temperature
    dewpoint_k = temp_k - 5.0

    # total_precipitation in metres, ACCUMULATED across the 3 hours (ERA5-Land convention)
    precip_m_accumulated = np.zeros(shape)
    precip_m_accumulated[0] = 0.001
    precip_m_accumulated[1] = 0.0025   # +0.0015 in hour 1
    precip_m_accumulated[2] = 0.0025   # +0 in hour 2 (no more rain)

    u_wind = np.full(shape, 2.0)
    v_wind = np.full(shape, 1.5)

    return xr.Dataset(
        {
            "2m_temperature": (["time", "latitude", "longitude"], temp_k),
            "2m_dewpoint_temperature": (["time", "latitude", "longitude"], dewpoint_k),
            "total_precipitation": (["time", "latitude", "longitude"], precip_m_accumulated),
            "10m_u_component_of_wind": (["time", "latitude", "longitude"], u_wind),
            "10m_v_component_of_wind": (["time", "latitude", "longitude"], v_wind),
        },
        coords={"time": times, "latitude": latitudes, "longitude": longitudes},
    )


def make_synthetic_era5_dataset_real_naming() -> xr.Dataset:
    """
    SYNTHETIC — same values as make_synthetic_era5_dataset(), but using the
    short variable names and "valid_time" coordinate that REAL CDS-delivered
    ERA5-Land files actually use on disk (confirmed 2026-09-21 against
    data/raw/era5_land/era5_land_pilot_202306.nc: variables t2m, d2m, tp,
    u10, v10; time coordinate "valid_time", not "time"). Used to test
    normalize_era5_land_file()'s real-name mapping without needing network
    access or real credentials.
    """
    base = make_synthetic_era5_dataset()
    renamed = base.rename({
        "time": "valid_time",
        "2m_temperature": "t2m",
        "2m_dewpoint_temperature": "d2m",
        "total_precipitation": "tp",
        "10m_u_component_of_wind": "u10",
        "10m_v_component_of_wind": "v10",
    })
    return renamed
