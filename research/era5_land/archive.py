"""
Handling for CDS responses delivered as a ZIP archive instead of a bare
NetCDF file.

Observed behaviour (real pilot download, 2026-09-21): a request with
"data_format": "netcdf" against the "reanalysis-era5-land" dataset came
back as a ZIP archive (PK\\x03\\x04 signature) containing a single member,
"data_0.nc" - even though cdsapi wrote it to a path ending in ".nc". This
module detects and corrects exactly that filename/content mismatch. It does
not parse, resample, or otherwise touch the scientific bytes inside - it
only moves them from "inside a zip" to "a real .nc file on disk".
"""

import shutil
import zipfile
from pathlib import Path


def ensure_netcdf(path: Path) -> Path:
    """
    Given a file cdsapi claims it wrote to `path`, guarantee that on return
    `path` is a real NetCDF file (i.e. xarray.open_dataset(path) and
    netCDF4.Dataset(path) both work), extracting it from a ZIP wrapper if
    necessary.

    - If `path` is not a ZIP archive, it is returned unchanged (the normal
      case for CDS requests/datasets that DO return a bare NetCDF file).
    - If `path` IS a ZIP archive:
        * every ".nc" member is read into memory (fine at this pilot's file
          sizes - tens of KB; revisit with streaming extraction if request
          sizes grow substantially)
        * the original ZIP is preserved, renamed to `path` with a `.zip`
          suffix instead of the misleading `.nc` one it arrived with
        * the FIRST ".nc" member is written back out at `path` itself, so
          callers with a fixed expected filename (e.g. run_normalize.py)
          keep working unchanged
        * any additional ".nc" members (not produced by the current single-
          file pilot request, but handled defensively) are written
          alongside as "<original-stem>__<member-name>" so nothing is
          silently dropped

    Raises ValueError if the file is a ZIP archive but contains no .nc
    member at all - this is treated as a real failure, not something to
    paper over.
    """
    path = Path(path)

    if not zipfile.is_zipfile(path):
        return path

    with zipfile.ZipFile(path) as archive:
        nc_members = [name for name in archive.namelist() if name.lower().endswith(".nc")]
        if not nc_members:
            raise ValueError(
                f"{path} is a ZIP archive but contains no .nc member. "
                f"Archive contents: {archive.namelist()}"
            )
        extracted = {name: archive.read(name) for name in nc_members}

    # The ZipFile handle above is closed (context manager exited) before we
    # touch `path` on disk - required on Windows, where an open file cannot
    # be moved/renamed.
    archive_path = path.with_suffix(".zip")
    shutil.move(str(path), str(archive_path))

    primary_member = nc_members[0]
    path.write_bytes(extracted[primary_member])

    for member_name in nc_members[1:]:
        sibling_path = path.parent / f"{path.stem}__{Path(member_name).name}"
        sibling_path.write_bytes(extracted[member_name])

    return path
