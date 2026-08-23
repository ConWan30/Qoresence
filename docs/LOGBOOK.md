# Session logbook (default OFF)

After a local session stops, write a short debrief from the **files already on disk**: events JSONL plus Foundry `clips/*.chapters.json`.

This is a one-shot file read. It does not subscribe to the live event bus, does not take a lobe lock, and does not run on the capture/streamer thread.

```powershell
python -m qoresence.cli --logbook --jsonl-path logs/events.jsonl
```

Optional: `QORESENCE_CLIPS_DIR` points at the clips folder (default `clips/`). Output is `logbook_<stem>.md` and `.json` next to the JSONL.

Do not pass `--play` with `--logbook`. Session-end only.
