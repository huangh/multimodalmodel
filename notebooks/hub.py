import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="MBTA script hub")


@app.cell(hide_code=True)
def _():
    import time
    import traceback
    import uuid

    import marimo as mo
    import polars as pl

    from multimodalmodel.hub import ScriptRegistry, UsageStore, default_scripts_root
    from multimodalmodel.hub.usage import default_db_path

    return (
        ScriptRegistry,
        UsageStore,
        default_db_path,
        default_scripts_root,
        mo,
        pl,
        time,
        traceback,
        uuid,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # MBTA script hub

    Pick a script below and it is executed and rendered **into this page**.
    Scripts are plain marimo notebooks kept in a nested folder; the hub scans
    that folder, so publishing a new plot means dropping a file in it.

    Every selection is logged, and the leaderboard at the bottom shows what the
    team actually uses.
    """)
    return


@app.cell(hide_code=True)
def _(mo, uuid):
    # One id per kernel — i.e. per browser session in `marimo run`. Used to
    # attribute usage and to keep repeat renders from inflating the counts.
    session_id = uuid.uuid4().hex[:12]
    # Viewers identify themselves with ?user=alice; falls back to anonymous.
    viewer = mo.query_params().get("user") or "anonymous"
    return session_id, viewer


@app.cell(hide_code=True)
def _(mo):
    rescan_button = mo.ui.button(label="↻ Rescan scripts", kind="neutral")
    search_box = mo.ui.text(placeholder="filter scripts…", full_width=True)
    return rescan_button, search_box


@app.cell(hide_code=True)
def _(ScriptRegistry, UsageStore, default_db_path, default_scripts_root, rescan_button):
    rescan_button.value  # depend on the button so clicking it re-scans

    scripts_root = default_scripts_root()
    registry = ScriptRegistry(scripts_root)
    store = UsageStore(default_db_path())
    return registry, scripts_root, store


@app.cell(hide_code=True)
def _(mo, registry):
    tag_filter = mo.ui.multiselect(
        options=registry.tags(), label="tags", full_width=True
    )
    return (tag_filter,)


@app.cell(hide_code=True)
def _(registry, search_box, store, tag_filter):
    usage_counts = store.counts()
    matches = registry.search(search_box.value or "", tag_filter.value or [])

    def _option_label(meta):
        uses = usage_counts.get(meta.script_id, 0)
        suffix = f"  · {uses} uses" if uses else ""
        broken = "  ⚠️" if meta.error else ""
        return f"{meta.label}{suffix}{broken}"

    # Most-used first inside the dropdown so popular plots surface themselves.
    ordered = sorted(
        matches,
        key=lambda m: (
            -usage_counts.get(m.script_id, 0),
            m.group_parts,
            m.title.lower(),
        ),
    )
    script_options = {_option_label(m): m.script_id for m in ordered}
    return ordered, script_options, usage_counts


@app.cell(hide_code=True)
def _(mo, script_options):
    script_dropdown = mo.ui.dropdown(
        options=script_options,
        value=next(iter(script_options), None),
        label="script",
        full_width=True,
    )
    return (script_dropdown,)


@app.cell(hide_code=True)
def _(mo, rescan_button, script_dropdown, search_box, tag_filter):
    mo.vstack(
        [
            mo.hstack([search_box, tag_filter], widths=[2, 1], gap=1),
            mo.hstack(
                [script_dropdown, rescan_button], widths=[4, 1], gap=1, align="end"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(script_dropdown):
    selected_id = script_dropdown.value
    return (selected_id,)


@app.cell(hide_code=True)
def _(logged, mo, ordered, registry, scripts_root, selected_id, store):
    logged  # refresh the "uses" count after this render is recorded

    if selected_id:
        _meta = registry.get(selected_id)
        _uses = store.counts().get(selected_id, 0)
        _tags = " ".join(f"`{t}`" for t in _meta.tags) or "_untagged_"
        header = mo.callout(
            mo.md(
                f"### {_meta.title}\n\n"
                f"{_meta.description or '_No description._'}\n\n"
                f"**path** `{_meta.path.relative_to(scripts_root)}` · "
                f"**tags** {_tags} · **uses** {_uses} · "
                f"[open standalone](/s/{selected_id})"
            ),
            kind="neutral",
        )
    else:
        header = mo.callout(
            mo.md(
                f"No scripts matched. Scripts root: `{scripts_root}` "
                f"({len(ordered)} shown)."
            ),
            kind="warn",
        )
    header
    return


@app.cell(hide_code=True)
def _(registry, selected_id, traceback):
    # Load the selected file into a fresh App. Kept in its own cell because
    # `App.embed()` may not be called by the cell that defines the app.
    script_app = None
    load_error = None
    if selected_id:
        try:
            script_app = registry.load(selected_id)
        except Exception:
            load_error = traceback.format_exc()
    return load_error, script_app


@app.cell
async def _(script_app, time, traceback):
    embed_result = None
    embed_error = None
    embed_ms = None
    if script_app is not None:
        _t0 = time.perf_counter()
        try:
            embed_result = await script_app.embed()
        except Exception:
            embed_error = traceback.format_exc()
        embed_ms = (time.perf_counter() - _t0) * 1000
    return embed_error, embed_ms, embed_result


@app.cell(hide_code=True)
def _(embed_error, embed_ms, load_error, selected_id, session_id, store, viewer):
    # Log the render. The store dedupes repeat records from the same session
    # within a short window, so interacting with an embedded script's widgets
    # (which re-runs this chain) counts as one use.
    logged = False
    if selected_id:
        logged = store.record(
            selected_id,
            user=viewer,
            session_id=session_id,
            duration_ms=embed_ms,
            error=(load_error or embed_error or None) and "render failed",
        )
    return (logged,)


@app.cell(hide_code=True)
def _(embed_error, embed_result, load_error, mo, selected_id):
    if load_error or embed_error:
        rendered = mo.vstack(
            [
                mo.callout(
                    mo.md(f"**{selected_id} failed to render.**"),
                    kind="danger",
                ),
                mo.accordion({"Traceback": mo.plain_text(load_error or embed_error)}),
            ]
        )
    elif embed_result is not None:
        rendered = embed_result.output
    else:
        rendered = mo.md("_Select a script to render it here._")
    rendered
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""---\n### What people use""")
    return


@app.cell(hide_code=True)
def _(logged, mo, pl, registry, store):
    logged  # recompute the leaderboard right after a render is recorded

    _rows = store.summary()
    if _rows:
        _titles = {m.script_id: m.title for m in registry.all()}
        leaderboard = pl.DataFrame(
            [
                {
                    "script": _titles.get(u.script_id, u.script_id),
                    "script_id": u.script_id,
                    "uses": u.uses,
                    "viewers": u.unique_users,
                    "last used": u.last_used_iso,
                    "errors": u.errors,
                }
                for u in _rows
            ]
        )
        board = mo.ui.table(leaderboard.to_dicts(), selection=None, page_size=10)
    else:
        leaderboard = pl.DataFrame()
        board = mo.md("_No usage recorded yet._")
    board
    return (leaderboard,)


@app.cell(hide_code=True)
def _(leaderboard, mo):
    if leaderboard.height:
        import plotly.graph_objects as go

        _top = leaderboard.head(10).reverse()
        _fig = go.Figure(
            go.Bar(
                x=_top["uses"].to_list(),
                y=_top["script"].to_list(),
                orientation="h",
                marker_color="#1f77b4",
            )
        )
        _fig.update_layout(
            title="Most-rendered scripts",
            xaxis_title="renders",
            height=120 + 32 * _top.height,
            margin=dict(l=8, r=8, t=48, b=8),
        )
        chart = mo.ui.plotly(_fig)
    else:
        chart = mo.md("")
    chart
    return


if __name__ == "__main__":
    app.run()
