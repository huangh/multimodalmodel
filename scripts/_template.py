# /// hub
# title = "Template — copy me"
# description = "Minimal example of a hub script. Files starting with _ are skipped by the registry, so this one never shows up in the dropdown."
# tags = ["meta"]
# ///
"""Template hub script.

Copy this file anywhere under `scripts/`, rename it without the leading
underscore, and it appears in the hub dropdown on the next rescan.

Rules of thumb:
  * It is a normal marimo notebook — `marimo edit scripts/<path>.py` works.
  * Keep the render cheap; anything hitting the network should sit behind a
    `mo.ui.run_button` so opening the script does not fire requests.
  * Declare `params` in the frontmatter for values the hub may inject via
    `app.embed(defs=...)`.
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="Template — copy me")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    knob = mo.ui.slider(1, 10, value=3, label="knob")
    knob
    return (knob,)


@app.cell
def _(knob, mo):
    mo.md(f"Knob is **{knob.value}**.")
    return


if __name__ == "__main__":
    app.run()
