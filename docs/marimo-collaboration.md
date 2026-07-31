# Does marimo have collaborative components?

Findings against **marimo 0.23.8** (the version pinned in this repo), from the
installed source plus marimo's docs and issue tracker.

## Short answer

There is no drop-in "Google-Docs for notebooks" component you can put in a
cell. What exists:

| Capability | State in 0.23.8 | Useful for the hub? |
|---|---|---|
| Multiple viewers of an app (`marimo run`) | **Works.** Every browser session gets its own kernel and its own copy of the notebook's state. | **Yes — this is what the hub is built on.** |
| Real-time collaborative *editing* (RTC v2) | Experimental, edit mode only, off by default. | No |
| Kiosk mode | Extra clients attach to an existing kernel and receive its outputs. | Maybe, for a shared "wall display" |
| Shared application state across viewers | Not provided. Nothing in marimo syncs one viewer's state to another. | Build it yourself (we use SQLite) |
| Presence / cursors / comments | Not in the open-source package. | No |

## Multi-viewer app mode — the part we rely on

`marimo/_server/resume_strategies.py` spells the difference out:

* `EditModeResumeStrategy` — "Only one session per file is allowed in edit
  mode." A second tab on `marimo edit` gets the *"Notebook already connected —
  another browser tab is already connected to the kernel. Take over session"*
  prompt that people mistake for a collaboration bug.
* `RunModeResumeStrategy` — "Multiple sessions can exist for the same file in
  run mode."

So `marimo run` (and `create_asgi_app`, which is run mode only) already serves
many concurrent users, each isolated. Ten people can open the hub, each pick a
different script, and nobody stomps on anybody. Isolation is per session, so
"collaboration" in the hub has to mean *shared server-side facts*, not shared
kernel state — which is exactly the usage log.

An experimental `isolate_apps` flag additionally runs each app in its own host
process to avoid `sys.modules` collisions between notebooks; worth turning on
if scripts start importing conflicting module versions.

## RTC v2 (real-time collaborative editing)

Present but experimental, and it is not what the hub needs:

* Enabled by `experimental.rtc_v2 = true` in `marimo.toml`
  (`marimo/_config/config.py`).
* Requires the `loro` CRDT package; `is_rtc_available()` returns false
  without it (`_server/api/endpoints/ws/ws_kernel_ready.py`).
* `_should_init_rtc()` requires `mode == SessionMode.EDIT` — it does nothing in
  run mode.
* It synchronizes **cell code** through a CRDT document. The kernel is still
  single; two editors share one execution state.
* WebSocket-only (disabled under SSE), and marimo's maintainers say on
  [discussion #8631](https://github.com/marimo-team/marimo/discussions/8631)
  that it is still under active development and not recommended yet.
  [Issue #8456](https://github.com/marimo-team/marimo/issues/8456) tracks the
  broader multi-user workspace request.

Conclusion: RTC is for two people editing one notebook's source, not for a
served analytics front end. Skip it.

## Kiosk mode

`?kiosk=true` on the websocket connection lets an additional client attach to
an existing session and receive its operations (with some message types
filtered in `ws_message_loop.py`). This is the closest thing to "watch what I
am doing" in the open-source package. It's a plausible follow-up if we want a
shared dashboard screen driven by one operator, but it is not per-user
interactive.

## What we build ourselves

The hub's collaborative behavior comes from server-side state that all the
independent sessions share:

* **`UsageStore` (SQLite, WAL).** Every render is an event; the leaderboard and
  the popularity ordering in the dropdown are queries over it. Because each
  viewer is a separate kernel process, this is the shared surface — one
  person's use makes a script rank higher in everyone else's dropdown.
* **`?user=` identity.** Enough to attribute usage. Behind an authenticating
  proxy, populate it from the proxy's header instead.
* **Shareable links.** `/s/<script_id>` gives each script its own URL to send
  around, which is the cheap version of "look at this plot" collaboration.

Natural extensions, none of which need marimo to change:

* Comments/annotations per script — another table, rendered next to the plot.
* "Trending this week" — already possible via `summary(since_days=7)`.
* Push updates (server-sent events → `mo.ui.refresh`) so a new script or a
  changed leaderboard appears without a rescan.
* Saved parameter sets per script, shared by URL query params, so a link
  reproduces someone else's view.
