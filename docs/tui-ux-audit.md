# TUI UX Audit — 2026-08-20

Audit of `tui.py` (Textual) covering the OpenCode harness addition, the episode
viewer, and the enhancement round (progress %, multi-run monitoring, product
preview). Items marked **fixed** were addressed.

## Enhancement round (latest)

1. **Live progress percentage per run** — new `RunProgress` parser consumes
   pipeline output (`PHASE n`, `[section] Day X: expanding section Y/Z`,
   `Chapter i/n`, `Episode saved:`) and renders bar + percent + stage in every
   run row: `[████░░░░░░] 47% · story · day 4/6 · section 2/5`.
   Anchors: outline 10%, story 70%, banner 2%, chapter prompts 16%, save 2%.
2. **Multi-run monitoring at a glance** — runs header shows live counts
   (`Runs (live) — 2 running · 1 finished · 1 failed`) and every row carries
   its own bar/stage, so parallel local + remote runs are readable without
   selecting each one.
3. **Final-product preview in the viewer** — three views on keys `1`/`2`/`3`:
   **Story** (full prose), **Prompts** (banner + every chapter's
   establishing/action/close-up shots with aspect ratio), **Info** (metadata
   fields, per-day word counts and chapter structure, raw JSON). Content is
   cached per episode; switching views is instant.

## Fixed previously

4. Episode viewer added (`v` library, `o` last episode) — output was previously
   unreadable from inside the TUI.
5. Health check moved off the UI thread (was a 5 s freeze).
6. Stop button now disables when nothing is running.
7. Finished runs surface their episode id and offer `o`.

## Recommended follow-ups (not yet done)

8. Selections not persisted across launches (harness/model/seed reset).
9. Remote SSH box always visible; collapse when unused on short terminals.
10. Runs rows may truncate on narrow terminals now that labels carry bars —
    consider two-line options or auto-hiding the harness prefix once running.
11. Inline base-URL override for all HTTP harnesses (currently remote-openai
    only; others need env vars).
12. Quit-time modal when runs are active (children survive quit today).
13. `n` binding for random seed + show the seed's title before launching.
14. Route token-meter lines into run rows instead of the shared log body.
15. Surface last error line in failed-run labels.
16. OpenCode path ignores temperature/top_p/max_tokens — documented in README;
    could also warn inline when that harness is selected.

## Verification

- `python -m compileall -q app.py run_creative_pipeline.py tui.py scripts src tests`
- `pytest`: 153 passed / 0 failed (8 new RunProgress tests)
- Textual `run_test` integration: viewer views switch and restore, prompts
  view renders banner + 30 chapter blocks, info view shows per-day structure,
  run labels render bar/%/stage, header counts update
