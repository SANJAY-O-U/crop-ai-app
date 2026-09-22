"""
Focused tests for the ZIP-containing-NetCDF bug: a real pilot download from
CDS came back as a ZIP archive (containing "data_0.nc") saved under a
misleading ".nc" filename. See research/era5_land/archive.py.
"""

import zipfile
from pathlib import Path

import pytest
import xarray as xr

from era5_land.archive import ensure_netcdf
from synthetic_fixtures import make_synthetic_era5_dataset


def _make_zip(tmp_path, zip_name, members: dict[str, bytes]) -> Path:
    zip_path = tmp_path / zip_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        for member_name, content in members.items():
            zf.writestr(member_name, content)
    return zip_path


def test_ensure_netcdf_passthrough_for_non_zip_file(tmp_path):
    path = tmp_path / "already_real.nc"
    path.write_bytes(b"not a zip, pretend this is raw netcdf bytes")

    result = ensure_netcdf(path)

    assert result == path
    assert path.read_bytes() == b"not a zip, pretend this is raw netcdf bytes"
    assert not (tmp_path / "already_real.zip").exists()


def test_ensure_netcdf_extracts_single_member_zip_and_renames_archive(tmp_path):
    fake_nc_bytes = b"\x89HDF\r\n\x1a\nFAKE-BUT-DISTINCT-NETCDF-PAYLOAD"
    zip_disguised_as_nc = _make_zip(tmp_path, "pilot.nc", {"data_0.nc": fake_nc_bytes})

    result = ensure_netcdf(zip_disguised_as_nc)

    # The requested .nc path now contains the real extracted bytes...
    assert result == zip_disguised_as_nc
    assert zip_disguised_as_nc.read_bytes() == fake_nc_bytes
    assert not zipfile.is_zipfile(zip_disguised_as_nc)

    # ...and the original archive was preserved under an honest .zip name,
    # not left (or duplicated) under the misleading .nc name.
    archive_path = tmp_path / "pilot.zip"
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == ["data_0.nc"]
        assert archive.read("data_0.nc") == fake_nc_bytes


def test_ensure_netcdf_raises_when_zip_has_no_nc_member(tmp_path):
    zip_path = _make_zip(tmp_path, "no_nc.nc", {"readme.txt": b"no netcdf here"})

    with pytest.raises(ValueError, match="contains no .nc member"):
        ensure_netcdf(zip_path)


def test_ensure_netcdf_handles_multiple_nc_members(tmp_path):
    zip_path = _make_zip(tmp_path, "multi.nc", {
        "data_0.nc": b"PRIMARY-MEMBER-BYTES",
        "data_1.nc": b"SECOND-MEMBER-BYTES",
    })

    result = ensure_netcdf(zip_path)

    assert result.read_bytes() == b"PRIMARY-MEMBER-BYTES"
    sibling = tmp_path / "multi__data_1.nc"
    assert sibling.exists()
    assert sibling.read_bytes() == b"SECOND-MEMBER-BYTES"


def test_ensure_netcdf_roundtrip_is_openable_by_xarray(tmp_path):
    """
    Closest reproduction of the real bug: a genuine NetCDF file, zipped up
    exactly like CDS's response, must come back out openable by xarray.
    """
    original_dataset = make_synthetic_era5_dataset()
    inner_nc_path = tmp_path / "data_0.nc"
    original_dataset.to_netcdf(inner_nc_path)

    zip_disguised_as_nc = tmp_path / "era5_land_pilot_202306.nc"
    with zipfile.ZipFile(zip_disguised_as_nc, "w") as zf:
        zf.write(inner_nc_path, arcname="data_0.nc")
    inner_nc_path.unlink()  # only the zip remains, mirroring the real CDS response

    result_path = ensure_netcdf(zip_disguised_as_nc)

    reopened = xr.open_dataset(result_path)
    try:
        assert set(reopened.data_vars) == set(original_dataset.data_vars)
        assert reopened["2m_temperature"].values.tolist() == original_dataset["2m_temperature"].values.tolist()
    finally:
        reopened.close()
