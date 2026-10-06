import tarfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

import h5py
import pytest
from pyproj import Proj

from custom_components.wolkenwart_regenradar.radar import (
    PROJECTION,
    RadarError,
    decode_archive,
    grid_cell,
    read_pixel,
)

T = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
P = Proj(PROJECTION)
LAT, LON = 48.8, 9.2


def frame(lead=0, value=101, change=None):
    buf = BytesIO()
    with h5py.File(buf, "w") as f:
        what = f.create_group("what")
        what.attrs.update(
            object="COMP", date=T.strftime("%Y%m%d"), time=T.strftime("%H%M%S")
        )
        ul = P(-500, 500, inverse=True)
        where = f.create_group("where")
        where.attrs.update(
            projdef=PROJECTION,
            xsize=1100,
            ysize=1200,
            xscale=1000.0,
            yscale=1000.0,
            UL_lon=ul[0],
            UL_lat=ul[1],
        )
        w = f.create_group("dataset1/what")
        for prefix, at in [
            ("start", T + timedelta(minutes=lead - 5)),
            ("end", T + timedelta(minutes=lead)),
        ]:
            w.attrs[prefix + "date"] = at.strftime("%Y%m%d")
            w.attrs[prefix + "time"] = at.strftime("%H%M%S")
        a = f.create_group("dataset1/data1/what")
        a.attrs.update(
            quantity="ACRR",
            gain=0.001,
            offset=-0.001,
            nodata=4294967295.0,
            undetect=0.0,
        )
        d = f.create_dataset(
            "dataset1/data1/data",
            shape=(1200, 1100),
            dtype="uint32",
            fillvalue=1,
            chunks=(100, 100),
            compression="gzip",
        )
        d[grid_cell(LAT, LON)] = value
        if change:
            change(f)
    return buf.getvalue()


def archive(leads=range(0, 121, 5), change=None):
    b = BytesIO()
    with tarfile.open(fileobj=b, mode="w") as t:
        for lead in leads:
            payload = frame(lead, change=change)
            info = tarfile.TarInfo("composite_rv_20261006_1200_%03d-hd5" % lead)
            info.size = len(payload)
            t.addfile(info, BytesIO(payload))
    return b.getvalue()


@pytest.mark.parametrize(
    "value,expected", [(0, 0.0), (1, 0.0), (101, 0.1), (2001, 2.0)]
)
def test_scale_and_undetect(value, expected):
    assert read_pixel(frame(value=value), T, 0, LAT, LON) == expected


def test_missing_is_not_dry():
    with pytest.raises(RadarError, match="No radar data"):
        read_pixel(frame(value=4294967295), T, 0, LAT, LON)


@pytest.mark.parametrize("row,col", [(0, 0), (1199, 1099), (858, 481), (500, 500)])
def test_grid_pixel_centers_and_north_south_orientation(row, col):
    lon, lat = P(col * 1000, -row * 1000, inverse=True)
    assert grid_cell(lat, lon) == (row, col)


@pytest.mark.parametrize(
    "lat,lon", [(0, 0), (90, 0), (float("nan"), 9), (48, float("inf"))]
)
def test_invalid_or_outside_locations(lat, lon):
    with pytest.raises((RadarError, ValueError)):
        grid_cell(lat, lon)


def test_archive_full_series():
    f = decode_archive(archive(), T, LAT, LON)
    assert len(f.amounts) == 25 and set(f.amounts) == {0.1}


@pytest.mark.parametrize("leads", [range(0, 120, 5), [0, 0], []])
def test_partial_and_duplicate_archives_rejected(leads):
    with pytest.raises(RadarError):
        decode_archive(archive(leads), T, LAT, LON)


@pytest.mark.parametrize(
    "path,key,value",
    [
        ("what", "time", "115500"),
        ("dataset1/what", "endtime", "120500"),
        ("dataset1/data1/what", "quantity", "DBZH"),
        ("where", "xscale", 2000),
        ("where", "projdef", PROJECTION.replace("+lon_0=10", "+lon_0=11")),
        ("dataset1/data1/what", "gain", float("nan")),
    ],
)
def test_bad_metadata_rejected(path, key, value):
    with pytest.raises(RadarError):
        read_pixel(
            frame(change=lambda f: f[path].attrs.__setitem__(key, value)),
            T,
            0,
            LAT,
            LON,
        )


def test_symlink_archive_never_extracts():
    b = BytesIO()
    with tarfile.open(fileobj=b, mode="w") as t:
        i = tarfile.TarInfo("composite_rv_20261006_1200_000-hd5")
        i.type = tarfile.SYMTYPE
        i.linkname = "/etc/passwd"
        t.addfile(i)
    with pytest.raises(RadarError):
        decode_archive(b.getvalue(), T, LAT, LON)


def test_external_hdf5_link_rejected():
    def change(f):
        del f["dataset1/data1/data"]
        f["dataset1/data1/data"] = h5py.ExternalLink("/etc/passwd", "data")

    with pytest.raises(RadarError, match="link"):
        read_pixel(frame(change=change), T, 0, LAT, LON)
