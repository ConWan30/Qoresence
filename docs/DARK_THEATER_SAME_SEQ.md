# Dark Theater + Same-Seq

Placeholder for Grok Build on `feat/dark-theater-same-seq`. This file is not the implementation.

## Dark Theater
`/deck.html` LIVE rides FrameHub/WebRTC like Mobile Glass (MJPEG fallback). Dark on `!has_frame`, blank/uniform frame, or title-presence not play. Never paint last-good BGR. Plane Dim sleeps the board on menu/pause.

## Same-Seq
Render rule, not a new lobe. Widgets carry `frame_seq`. Paint only if `widget.frame_seq == live.frame_seq`. Mismatch ghosts (opacity 0 / empty). No stale digits.

## Out of scope
Ghost Stick, Clutch Ring, Glance Glyph. No new lobe flags. No QorTroller / PoAC / *-truth path. No invented scores. Optional lobes stay OFF.

## Done when
Blank or seq-skewed LIVE goes dark; scorebug from seq N cannot sit on frame N+k; tests for blank, seq skew, plane dim; freeze_events_excluding_deck_lock no longer treats last-good LIVE paint as accepted; short doc note in RETINA_DECK_UIUX / WEBRTC_LIVE / TITLE_PRESENCE.
