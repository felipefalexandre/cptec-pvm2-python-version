"""NetCDF input/output with configurable variable names."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..core.constants import IPAR_TO_EINSTEIN

try:
    import xarray as xr
except ImportError:  # pragma: no cover
    xr = None

REQUIRED = ("precipitation", "temperature", "par", "pressure", "landmask", "uwind")


def _require_xarray():
    if xr is None:
        raise ImportError("xarray is required for NetCDF input/output")


def _drop_duplicate_longitude(da, lon_name, policy):
    if policy in (None, "keep"):
        return da
    if policy != "drop_last":
        raise ValueError(f"unknown longitude duplicate policy: {policy}")
    lon = da[lon_name].values
    if lon.size < 2:
        return da
    if np.isclose(lon[0] % 360.0, lon[-1] % 360.0):
        return da.isel({lon_name: slice(0, -1)})
    return da


def _to_time_lat_lon(da, time_name, lat_name, lon_name):
    dims = list(da.dims)
    if len(dims) != 3:
        raise ValueError(f"variable {da.name!r} must be 3-D, got dims {dims}")
    present = {time_name, lat_name, lon_name}
    if set(dims) != present:
        raise ValueError(
            f"variable {da.name!r} dims {dims} do not match configured "
            f"coordinates {sorted(present)}"
        )
    if time_name != dims[0]:
        da = da.transpose(time_name, lat_name, lon_name)
    return da


def _to_lat_lon(da, time_name, lat_name, lon_name):
    """Accept a static field as 2-D or as a constant 3-D field."""
    if time_name in da.dims:
        if da.sizes[time_name] > 1:
            first = da.isel({time_name: 0})
            if not np.allclose(da.values, first.values, equal_nan=True):
                raise ValueError(
                    f"static variable {da.name!r} varies over time"
                )
        da = da.isel({time_name: 0})
    dims = list(da.dims)
    present = {lat_name, lon_name}
    if set(dims) != present:
        raise ValueError(
            f"static variable {da.name!r} dims {dims} do not match "
            f"coordinates {sorted(present)}"
        )
    if dims != [lat_name, lon_name]:
        da = da.transpose(lat_name, lon_name)
    return da


def _to_celsius(da, units):
    units = (units or "").strip().lower().replace(" ", "")
    if units in ("degc", "°c", "c", "celsius", "degrees_celsius"):
        return da
    if units in ("k", "kelvin"):
        out = da - 273.15
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "degC"
        out.attrs["comment"] = "converted from K by subtracting 273.15"
        return out
    raise ValueError(f"unsupported temperature units: {units!r}")


def _to_hpa(da, units):
    key = (units or "").strip().lower().replace(" ", "")
    if key in ("", "hpa", "mb", "mbar", "millibar", "hectopascal"):
        return da
    if key in ("pa", "pascal"):
        out = da / 100.0
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "hPa"
        out.attrs["comment"] = "converted from Pa"
        return out
    if key in ("kpa", "kilopascal"):
        out = da * 10.0
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "hPa"
        out.attrs["comment"] = "converted from kPa"
        return out
    raise ValueError(f"unsupported pressure units: {units!r}")


def _to_wm2(da, units):
    key = (units or "").strip().lower().replace(" ", "")
    if key in (
        "",
        "wm-2",
        "w/m2",
        "w/m^2",
        "wm^-2",
        "wm-2sr-1",
        "wattm-2",
    ):
        return da
    if key in ("einsteinm-2s-1", "einstein/m2/s", "em-2s-1"):
        out = da * IPAR_TO_EINSTEIN
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "W m-2"
        out.attrs["comment"] = "converted from Einstein m-2 s-1"
        return out
    raise ValueError(f"unsupported PAR units: {units!r}")


MONTH_LENGTH_DAYS = np.array(
    [31.0, 28.25, 31.0, 30.0, 31.0, 30.0, 31.0, 31.0, 30.0, 31.0, 30.0, 31.0]
)


def _to_mm_per_month(da, units, time_name):
    key = (units or "").strip().lower().replace(" ", "")
    if key in ("mm/month", "mmmonth-1", "mmmonth^-1", "mm"):
        return da
    if key in ("m/month", "mmonth-1", "mmonth^-1", "m"):
        out = da * 1000.0
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "mm/month"
        return out
    if key in ("mm/day", "mmday-1", "mmd-1", "mm/d"):
        seconds = xr.DataArray(
            MONTH_LENGTH_DAYS,
            dims=(time_name,),
            coords={time_name: da[time_name]},
        )
        out = da * seconds
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "mm/month"
        out.attrs["comment"] = "converted from mm day-1 using monthly day counts"
        return out
    if key in ("m/day", "mday-1", "md-1", "m/d"):
        seconds = xr.DataArray(
            1000.0 * MONTH_LENGTH_DAYS,
            dims=(time_name,),
            coords={time_name: da[time_name]},
        )
        out = da * seconds
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "mm/month"
        out.attrs["comment"] = "converted from m day-1 using monthly day counts"
        return out
    if key in ("kgm-2s-1", "kg/m2/s", "kgm^-2s^-1", "kgm-2/s"):
        seconds = xr.DataArray(
            86400.0 * MONTH_LENGTH_DAYS,
            dims=(time_name,),
            coords={time_name: da[time_name]},
        )
        out = da * seconds
        out.attrs = dict(da.attrs)
        out.attrs["units"] = "mm/month"
        out.attrs["comment"] = "converted from kg m-2 s-1 using monthly day counts"
        return out
    raise ValueError(f"unsupported precipitation units: {units!r}")


def load_field(path, key, variable, coords, units=None, lon_duplicate="drop_last"):
    """Load one variable from NetCDF, convert units and return grid metadata."""
    _require_xarray()
    time_name = coords.get("time", "time")
    lat_name = coords.get("latitude", "lat")
    lon_name = coords.get("longitude", "lon")

    with xr.open_dataset(path, decode_times=False) as ds:
        if variable not in ds:
            raise KeyError(f"variable {variable!r} not found in {path}")
        da = ds[variable]
        static = key in ("pressure", "landmask")
        if static:
            da = _to_lat_lon(da, time_name, lat_name, lon_name)
        else:
            da = _to_time_lat_lon(da, time_name, lat_name, lon_name)
        da = _drop_duplicate_longitude(da, lon_name, lon_duplicate)
        if not static and da.sizes[time_name] != 12:
            raise ValueError(
                f"{variable!r} has {da.sizes[time_name]} time steps; "
                "PVM2 requires a monthly climatology of exactly 12"
            )
        if key == "temperature":
            da = _to_celsius(da, units or da.attrs.get("units"))
        if key == "pressure":
            da = _to_hpa(da, units or da.attrs.get("units"))
        if key == "par":
            da = _to_wm2(da, units or da.attrs.get("units"))
        if key == "precipitation":
            da = _to_mm_per_month(
                da, units or da.attrs.get("units"), time_name
            )
        if static:
            da = da.transpose(lat_name, lon_name)
        else:
            da = da.transpose(time_name, lat_name, lon_name)
        values = np.asarray(da.values, dtype=np.float64)
        values = np.where(values <= -1.0e30, np.nan, values)
        lat = np.asarray(ds[lat_name].values, dtype=np.float64)
        lon = np.asarray(ds[lon_name].values, dtype=np.float64)
        if lon_duplicate == "drop_last" and lon.size > 1:
            if np.isclose(lon[0] % 360.0, lon[-1] % 360.0):
                lon = lon[:-1]
        attrs = {
            "source_variable": variable,
            "units": da.attrs.get("units"),
            "source_file": str(path),
        }
    return {"values": values, "lat": lat, "lon": lon, "attrs": attrs}


def load_climate(path, mapping, coords, units=None, lon_duplicate="drop_last"):
    """Load a 12-month climatology from NetCDF into model arrays."""
    _require_xarray()
    units = units or {}
    out = {}
    attrs = {}
    lat = lon = None
    for key in REQUIRED:
        if key not in mapping:
            raise KeyError(f"missing variable mapping for {key!r}")
        field = load_field(
            path,
            key,
            mapping[key],
            coords,
            units.get(key),
            lon_duplicate,
        )
        out[key] = field["values"]
        attrs[key] = field["attrs"]
        if lat is None:
            lat, lon = field["lat"], field["lon"]
        elif not (
            np.allclose(lat, field["lat"], equal_nan=True)
            and np.allclose(lon, field["lon"], equal_nan=True)
        ):
            raise ValueError(
                f"{path}: variables are not on the same latitude/longitude grid"
            )
    out["lat"] = lat
    out["lon"] = lon
    out["attrs"] = attrs
    return out


def _write_grid_mapping(ds, lat, lon):
    ds["crs"] = xr.DataArray(
        np.int32(0),
        attrs={
            "grid_mapping_name": "latitude_longitude",
            "longitude_of_prime_meridian": 0.0,
            "semi_major_axis": 6378137.0,
            "inverse_flattening": 298.257223563,
            "spatial_ref": (
                'GEOGCS["WGS 84",DATUM["WGS_1984",'
                'SPHEROID["WGS 84",6378137,298.257223563]],'
                'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
            ),
        },
    )


def write_outputs(path, results, lat, lon, run_attrs=None):
    """Write the complete PVM2 result set to a CF-style NetCDF file."""
    _require_xarray()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    coords = {"time": np.arange(1, 13), "lat": lat, "lon": lon}

    monthly = {
        "npp": ("Net primary productivity", "kgC m-2 yr-1"),
        "gpp": ("Canopy gross photosynthesis", "kgC m-2 yr-1"),
        "ra": ("Autotrophic respiration", "kgC m-2 yr-1"),
        "rh": ("Heterotrophic respiration", "kgC m-2 yr-1"),
        "soilmoist": ("Degree of soil saturation (W)", "1"),
        "evapotranspiration": ("Actual evapotranspiration", "mm day-1"),
        "canopy_resistance": ("Canopy resistance", "s m-1"),
        "lai": ("Leaf area index", "m2 m-2"),
    }
    annual_map = {
        "tmin": ("Minimum monthly air temperature", "degC", "tmin"),
        "meanpp": ("Mean annual NPP", "kgC m-2 yr-1", "meanpp"),
        "seanpp": ("NPP seasonality index (S)", "1", "seanpp"),
        "meanhr": ("Mean annual heterotrophic respiration", "kgC m-2 yr-1", "meanhr"),
        "meancs": ("Mean annual soil carbon", "kgC m-2", "meancs"),
        "mphoto": ("Mean annual gross photosynthesis", "kgC m-2 yr-1", "mphoto"),
        "maresp": ("Mean annual autotrophic respiration", "kgC m-2 yr-1", "maresp"),
        "seai": ("Seasonality index (D)", "1", "seai"),
        "weti": ("Wetness index (H)", "1", "weti"),
        "ratioNPP": ("NPP/IPAR ratio (R)", "1", "ratioNPP"),
        "d2wm": ("Dry-to-wet transition month", "1", "d2wm"),
        "ud2w": ("850 hPa zonal wind after transition", "m s-1", "ud2w"),
    }

    data_vars = {}
    bpot = results["bpot"].astype(np.int16)
    data_vars["biome"] = (
        ("lat", "lon"),
        bpot,
        {
            "long_name": "Potential natural vegetation biome",
            "flag_values": np.arange(0, 21, dtype=np.int16),
            "flag_meanings": (
                "ocean ombrophyllous_forest temperate_forest mixed_forest "
                "boreal_forest larch savanna grasslands caatinga semi_desert "
                "tundra desert seasonal_forest ice"
            ),
            "grid_mapping": "crs",
        },
    )
    for name, (long_name, units, key) in annual_map.items():
        data_vars[name] = (
            ("lat", "lon"),
            np.asarray(results[key], dtype=np.float64),
            {"long_name": long_name, "units": units, "grid_mapping": "crs"},
        )
    for name, (long_name, units) in monthly.items():
        key = {
            "npp": "mnpp",
            "gpp": "photo",
            "ra": "aresp",
            "rh": None,
            "soilmoist": "wsoil2",
            "evapotranspiration": "evaptr",
            "canopy_resistance": "rc",
            "lai": "lai",
        }[name]
        if key is None:
            continue
        data_vars[name] = (
            ("time", "lat", "lon"),
            np.asarray(results[key], dtype=np.float64),
            {"long_name": long_name, "units": units, "grid_mapping": "crs"},
        )

    ds = xr.Dataset(data_vars, coords=coords)
    _write_grid_mapping(ds, lat, lon)
    ds["lat"].attrs = {"standard_name": "latitude", "units": "degrees_north"}
    ds["lon"].attrs = {"standard_name": "longitude", "units": "degrees_east"}
    ds["time"].attrs = {"long_name": "climatological month", "units": "1"}
    ds.attrs.update(
        {
            "title": "CPTEC-PVM2 potential vegetation",
            "source": "pvm2 (Python reference implementation)",
            "Conventions": "CF-1.10",
            "history": "Created by pvm2",
        }
    )
    if run_attrs:
        ds.attrs.update({k: str(v) for k, v in run_attrs.items()})
    ds.to_netcdf(path)
    return path

def write_inputs(path, data, attrs=None):
    """Write a consolidated PVM2 climate input file (12-month climatology)."""
    _require_xarray()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lat = np.asarray(data["lat"], dtype=np.float64)
    lon = np.asarray(data["lon"], dtype=np.float64)
    coords = {"time": np.arange(1, 13), "lat": lat, "lon": lon}
    data_vars = {}
    monthly = {
        "precipitation": ("pr", "precipitation_amount", "mm/month"),
        "temperature": ("tas", "air_temperature", "degC"),
        "par": ("par", "surface_downwelling_photosynthetic_radiative_flux", "W m-2"),
        "uwind": ("ua850", "eastward_wind", "m s-1"),
    }
    for key, (name, long_name, units) in monthly.items():
        data_vars[name] = (
            ("time", "lat", "lon"),
            np.asarray(data[key], dtype=np.float32),
            {
                "long_name": long_name,
                "units": units,
                "cell_methods": "time: mean",
                "grid_mapping": "crs",
            },
        )
    for key, (name, long_name, units) in {
        "pressure": ("ps", "surface_air_pressure", "hPa"),
        "landmask": ("lsmk", "land_binary_mask", "1"),
    }.items():
        data_vars[name] = (
            ("lat", "lon"),
            np.asarray(data[key], dtype=np.float32),
            {"long_name": long_name, "units": units, "grid_mapping": "crs"},
        )
    ds = xr.Dataset(data_vars, coords=coords)
    _write_grid_mapping(ds, lat, lon)
    ds["lat"].attrs = {"standard_name": "latitude", "units": "degrees_north"}
    ds["lon"].attrs = {"standard_name": "longitude", "units": "degrees_east"}
    ds["time"].attrs = {"long_name": "climatological month", "units": "1"}
    ds.attrs.update(
        {
            "title": "PVM2 input climatology",
            "Conventions": "CF-1.10",
            "source": "pvm2 convert-legacy",
        }
    )
    if attrs:
        ds.attrs.update({k: str(v) for k, v in attrs.items()})
    ds.to_netcdf(path)
    return path


def summarize(path):
    """Return a JSON-serialisable summary of a NetCDF file."""
    _require_xarray()
    with xr.open_dataset(path, decode_times=False) as ds:
        return {
            "path": str(path),
            "dimensions": dict(ds.sizes),
            "variables": {
                name: {
                    "dims": list(da.dims),
                    "shape": list(da.shape),
                    "units": da.attrs.get("units"),
                }
                for name, da in ds.data_vars.items()
            },
            "coordinates": list(ds.coords),
        }
