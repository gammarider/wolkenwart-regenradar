"""DWD RV reader written against ODIM H5 and DWD format specifications.

No code from another Home Assistant integration is used here. Coordinate
transforms use PROJ; ODIM matrices are ordered west-east, then north-south.
"""

import math
import re
import tarfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

import aiohttp
import h5py
from pyproj import Proj

from .core import Forecast

MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
PROJECTION = "+proj=stere +lat_ts=60 +lat_0=90 +lon_0=10 +x_0=543196.83521776402 +y_0=3622588.8619310022 +units=m +a=6378137 +b=6356752.3142451802 +no_defs"


class RadarError(ValueError):
    """Unusable or incomplete weather data."""


def text(value):
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def timestamp(attrs, prefix):
    return datetime.strptime(
        text(attrs[prefix + "date"]) + text(attrs[prefix + "time"]), "%Y%m%d%H%M%S"
    ).replace(tzinfo=UTC)


def grid_cell(latitude: float, longitude: float, where=None):
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise RadarError("Invalid location")
    # Restrict to the published DWD WGS84 DE1200 grid. No metadata-driven
    # external projection grids, file reads or network lookups.
    projection = Proj(PROJECTION)
    x, y = projection(longitude, latitude)
    if where is None:
        west, north = -500.0, 500.0
    else:
        if (int(where["xsize"]), int(where["ysize"])) != (1100, 1200):
            raise RadarError("Unsupported radar grid")
        if float(where["xscale"]) != 1000 or float(where["yscale"]) != 1000:
            raise RadarError("Unsupported pixel scale")
        # Require the standard projection parameters before interpreting data.
        params = dict(re.findall(r"\+(\w+)=([^\s]+)", text(where["projdef"])))
        expected = dict(re.findall(r"\+(\w+)=([^\s]+)", PROJECTION))
        for key in ("lat_ts", "lat_0", "lon_0", "x_0", "y_0", "a", "b"):
            if not math.isclose(
                float(params.get(key, "nan")),
                float(expected[key]),
                rel_tol=1e-10,
                abs_tol=1e-5,
            ):
                raise RadarError("Unsupported projection")
        if params.get("proj") != "stere" or params.get("units", "m") != "m":
            raise RadarError("Unsupported projection")
        west, north = projection(float(where["UL_lon"]), float(where["UL_lat"]))
        if abs(west + 500) > 1 or abs(north - 500) > 1:
            raise RadarError("Unexpected grid origin")
    row, col = math.floor((north - y) / 1000), math.floor((x - west) / 1000)
    if not (0 <= row < 1200 and 0 <= col < 1100):
        raise RadarError("Location outside DWD coverage")
    return row, col


def read_pixel(payload: bytes, release: datetime, lead: int, lat: float, lon: float):
    try:
        with h5py.File(BytesIO(payload), "r") as data:
            # Reject links: all needed metadata and data must reside in this file.
            for path in (
                "what",
                "where",
                "dataset1",
                "dataset1/what",
                "dataset1/data1",
                "dataset1/data1/what",
                "dataset1/data1/data",
            ):
                if not isinstance(data.get(path, getlink=True), h5py.HardLink):
                    raise RadarError("Unsupported HDF5 link")
            if text(data["what"].attrs["object"]) != "COMP":
                raise RadarError("Not a composite")
            if timestamp(data["what"].attrs, "") != release:
                raise RadarError("Wrong source release")
            window = data["dataset1/what"].attrs
            if timestamp(window, "end") != release + timedelta(
                minutes=lead
            ) or timestamp(window, "start") != release + timedelta(minutes=lead - 5):
                raise RadarError("Unexpected forecast window")
            what = data["dataset1/data1/what"].attrs
            if text(what["quantity"]) != "ACRR":
                raise RadarError("Not accumulated precipitation")
            grid = data["dataset1/data1/data"]
            if (
                grid.shape != (1200, 1100)
                or grid.dtype.kind != "u"
                or grid.dtype.itemsize != 4
                or grid.is_virtual
                or grid.external
            ):
                raise RadarError("Unsupported data matrix")
            row, col = grid_cell(lat, lon, data["where"].attrs)
            raw = int(grid[row, col])
            if raw == float(what["nodata"]):
                raise RadarError("No radar data for location")
            gain, offset = float(what["gain"]), float(what["offset"])
            if not math.isfinite(gain) or gain <= 0 or not math.isfinite(offset):
                raise RadarError("Invalid radar scaling")
            value = 0.0 if raw == float(what["undetect"]) else raw * gain + offset
            if not math.isfinite(value) or value < 0:
                raise RadarError("Invalid radar value")
            return round(value, 6)
    except (KeyError, OSError, TypeError) as err:
        raise RadarError("Invalid radar file") from err


def decode_archive(blob: bytes, release: datetime, lat: float, lon: float) -> Forecast:
    if len(blob) > MAX_DOWNLOAD:
        raise RadarError("Radar archive too large")
    prefix = "composite_rv_" + release.strftime("%Y%m%d_%H%M")
    expected = {f"{prefix}_{lead:03d}-hd5": lead for lead in range(0, 121, 5)}
    values = {}
    try:
        with tarfile.open(fileobj=BytesIO(blob), mode="r:") as archive:
            for member in archive:
                if (
                    member.name not in expected
                    or not member.isfile()
                    or not 0 < member.size <= MAX_MEMBER
                ):
                    raise RadarError("Unexpected archive member")
                lead = expected[member.name]
                if lead in values:
                    raise RadarError("Duplicate forecast window")
                with archive.extractfile(member) as stream:
                    values[lead] = read_pixel(
                        stream.read(MAX_MEMBER + 1), release, lead, lat, lon
                    )
        if len(values) != 25:
            raise RadarError("Incomplete forecast")
        return Forecast(release, tuple(values[k] for k in sorted(values)))
    except (tarfile.TarError, EOFError) as err:
        raise RadarError("Invalid radar archive") from err


async def download(session: aiohttp.ClientSession, release: datetime) -> bytes:
    stamp = release.strftime("%Y%m%d_%H%M")
    url = f"https://opendata.dwd.de/weather/radar/composite/rv/composite_rv_{stamp}.tar"
    async with session.get(
        url, timeout=aiohttp.ClientTimeout(total=45), allow_redirects=False
    ) as response:
        if response.status != 200:
            raise RadarError(f"DWD HTTP {response.status}")
        if (
            response.content_length is not None
            and response.content_length > MAX_DOWNLOAD
        ):
            raise RadarError("Radar archive too large")
        content = bytearray()
        async for chunk in response.content.iter_chunked(256 * 1024):
            content.extend(chunk)
            if len(content) > MAX_DOWNLOAD:
                raise RadarError("Radar archive too large")
        return bytes(content)
