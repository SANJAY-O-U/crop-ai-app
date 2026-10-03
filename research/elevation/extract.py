"""
Zonal elevation statistics for one GP polygon against a Copernicus DEM
GLO-30 raster mosaic.

METHODOLOGY (documented exactly, per the Stage requirement to be explicit
about sampling behavior):

  CRS transformation
  -------------------
  Copernicus DEM GLO-30 tiles are natively EPSG:4326 (WGS84 geographic),
  confirmed this session via `rasterio.open(...).crs` on the downloaded
  tiles. The Yelandur spatial-proxy geometries are also WGS84 (see
  research/spatial_proxy/README.md's CRS section). Both inputs are
  therefore already in the same CRS -- NO reprojection is performed before
  sampling. Elevation values (metres) and zonal statistics derived from
  them (mean/min/max/std) are scale-invariant under reprojection anyway, so
  no projected CRS is needed for correctness here. (Had this module needed
  a physical area or distance -- it doesn't -- EPSG:32643 / UTM 43N would
  be the appropriate projected CRS, matching the convention already used in
  research/spatial_proxy/build.py.)

  Pixel inclusion / intersection behavior
  ----------------------------------------
  Statistics are PIXEL-CENTER based, not area/intersection-weighted:
  rasterstats.zonal_stats is called with the default `all_touched=False`,
  meaning a DEM pixel is included in a GP's sample if and only if that
  pixel's CENTER falls inside (or on the boundary of) the GP polygon. A
  pixel that the polygon merely clips at its edge, without covering the
  pixel's center, is excluded. This under-samples polygon edges slightly
  but avoids double-counting a pixel across two adjacent GPs, which matters
  here since several Yelandur GPs share borders.

  nodata handling
  ----------------
  The downloaded COG tiles report no embedded GDAL nodata tag
  (`rasterio.open(...).nodata is None`, confirmed this session for both
  tiles used here) -- expected, since Copernicus DEM only omits data over
  ocean/unreleased tiles, and this AOI is fully inland. As a defensive
  check, every tile was scanned for common DSM sentinel values (e.g.
  -32767, -9999) before use; none were found (observed tile-wide minimum
  elevation was +112m). rasterstats itself requires SOME nodata value for
  its internal boundless-window masking machinery and defaults to -999
  with a warning if given None; this module passes -999 explicitly
  instead, which is functionally "no masking" for this AOI since no real
  DSM pixel here is anywhere near -999. sample_count therefore equals the
  literal count of pixel centers inside the polygon, with no real pixels
  excluded.

  Units
  -----
  Elevation values are metres (Copernicus DEM's native unit; no conversion
  applied). Coordinates are decimal degrees (WGS84).
"""

import rasterio
import rasterio.merge
import rasterstats

DEM_NODATA = -999.0  # rasterstats' own required sentinel; see "nodata handling" above -- never
                      # collides with real DSM values in this AOI (observed tile-wide min: +112m)
ZONAL_STATS = ["mean", "min", "max", "std", "count"]


def load_mosaic(tile_paths: list):
    """Merges the given DEM tile GeoTIFFs into a single in-memory array +
    affine transform. Small enough here (2 tiles, 3600x3600 float32 each)
    to hold fully in memory -- this is not meant to scale beyond a single
    taluk's worth of tiles."""
    datasets = [rasterio.open(p) for p in tile_paths]
    try:
        crs = datasets[0].crs
        for ds in datasets:
            if ds.crs != crs:
                raise ValueError(f"tile CRS mismatch: {ds.crs} vs {crs}")
        mosaic, transform = rasterio.merge.merge(datasets)
    finally:
        for ds in datasets:
            ds.close()
    return mosaic[0], transform, crs  # band 1 (single-band DSM)


def compute_zonal_stats(geometry: dict, mosaic_array, transform, nodata=DEM_NODATA) -> dict:
    """Computes mean/min/max/range/std/sample_count for one GeoJSON-like
    polygon/multipolygon geometry against the given DEM mosaic array.
    Returns all-None stats (sample_count=0) if no pixel center falls inside
    the geometry -- never fabricates a value for an empty sample."""
    results = rasterstats.zonal_stats(
        geometry,
        mosaic_array,
        affine=transform,
        nodata=nodata,
        stats=ZONAL_STATS,
        all_touched=False,  # pixel-CENTER inclusion -- see module docstring
    )
    stats = results[0]
    count = stats["count"] or 0

    if count == 0:
        return {
            "mean_m": None, "min_m": None, "max_m": None,
            "range_m": None, "std_m": None, "sample_count": 0,
        }

    mean_m, min_m, max_m, std_m = stats["mean"], stats["min"], stats["max"], stats["std"]
    return {
        "mean_m": float(mean_m),
        "min_m": float(min_m),
        "max_m": float(max_m),
        "range_m": float(max_m - min_m),
        "std_m": float(std_m),
        "sample_count": int(count),
    }
