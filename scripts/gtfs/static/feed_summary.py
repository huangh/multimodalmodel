# /// hub
# title = "GTFS feed summary"
# description = "Row counts and agency/route breakdown for a static GTFS zip or extracted directory."
# tags = ["gtfs", "static", "offline"]
# params = ["gtfs_path"]
# ///
import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="GTFS feed summary")


@app.cell
def _():
    import io
    import os
    import zipfile
    from pathlib import Path

    import marimo as mo
    import polars as pl

    return Path, io, mo, os, pl, zipfile


@app.cell
def _(os):
    # Overridable by the hub via app.embed(defs={"gtfs_path": ...}).
    gtfs_path = os.environ.get("GTFS_PATH", "")
    return (gtfs_path,)


@app.cell
def _(gtfs_path, mo):
    path_input = mo.ui.text(
        value=gtfs_path,
        placeholder="/path/to/gtfs.zip or extracted folder",
        label="GTFS feed",
        full_width=True,
    )
    path_input
    return (path_input,)


@app.cell
def _(Path, io, path_input, pl, zipfile):
    def read_table(feed: str, name: str) -> pl.DataFrame:
        """Read one GTFS table from a zip or a directory, empty if absent."""
        p = Path(feed).expanduser()
        if p.is_dir():
            f = p / name
            return (
                pl.read_csv(f, infer_schema_length=0) if f.exists() else pl.DataFrame()
            )
        if p.is_file() and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as zf:
                if name not in zf.namelist():
                    return pl.DataFrame()
                return pl.read_csv(io.BytesIO(zf.read(name)), infer_schema_length=0)
        return pl.DataFrame()

    feed_path = path_input.value.strip()
    return feed_path, read_table


@app.cell
def _(feed_path, mo, pl, read_table):
    mo.stop(not feed_path, mo.md("Point this at a GTFS zip or folder to summarize it."))

    TABLES = [
        "agency.txt",
        "routes.txt",
        "trips.txt",
        "stops.txt",
        "stop_times.txt",
        "calendar.txt",
        "shapes.txt",
    ]
    tables = {name: read_table(feed_path, name) for name in TABLES}
    counts = pl.DataFrame([{"table": n, "rows": df.height} for n, df in tables.items()])
    return counts, tables


@app.cell
def _(counts, mo, pl, tables):
    _routes = tables["routes.txt"]
    _trips = tables["trips.txt"]

    _by_type = pl.DataFrame()
    if _routes.height and "route_type" in _routes.columns:
        _by_type = _routes.group_by("route_type").len().sort("len", descending=True)

    _busiest = pl.DataFrame()
    if _trips.height and "route_id" in _trips.columns:
        _busiest = (
            _trips.group_by("route_id")
            .len()
            .rename({"len": "trips"})
            .sort("trips", descending=True)
            .head(15)
        )

    mo.vstack(
        [
            mo.md("#### Table sizes"),
            mo.ui.table(counts.to_dicts(), selection=None),
            mo.md("#### Routes by type"),
            mo.ui.table(_by_type.to_dicts(), selection=None)
            if _by_type.height
            else mo.md("_no routes.txt_"),
            mo.md("#### Busiest routes by trip count"),
            mo.ui.table(_busiest.to_dicts(), selection=None)
            if _busiest.height
            else mo.md("_no trips.txt_"),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
