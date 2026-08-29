import assert from "node:assert/strict";
import { test } from "node:test";
import { parseMatchAgentNote } from "./match-agent.ts";

test("missing field is fail-closed empty", () => {
  assert.equal(parseMatchAgentNote(undefined), null);
  assert.equal(parseMatchAgentNote(null), null);
  assert.equal(parseMatchAgentNote({ schema_version: "qoresence-deck-v0" }), null);
});

test("empty {} is fail-closed empty", () => {
  assert.equal(parseMatchAgentNote({}), null);
  assert.equal(parseMatchAgentNote({ match_agent: {} }), null);
});

test("!ok / !live / unlicensed / hold / empty text stay empty", () => {
  const licensed = {
    ok: true,
    live: true,
    text: "DAL 21 NO 13 on this frame",
    ticket_id: "t1",
    path: "confirm",
    model: "deepseek",
  };
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, ok: false } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, live: false } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, ticket_id: "" } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, path: "hold" } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, path: "slow" } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, text: "" } }), null);
  assert.equal(parseMatchAgentNote({ match_agent: { ...licensed, text: "   " } }), null);
});

test("licensed path=confirm shows text without inventing scores", () => {
  const note = parseMatchAgentNote({
    match_agent: {
      ok: true,
      live: true,
      text: "DAL 21 NO 13 on this frame",
      ticket_id: "t1",
      path: "confirm",
      model: "deepseek",
    },
  });
  assert.ok(note);
  assert.equal(note.text, "DAL 21 NO 13 on this frame");
  assert.equal(note.path, "confirm");
  assert.equal(note.ticketId, "t1");
  assert.equal("score" in note, false);
  assert.equal("homeScore" in note, false);
});

test("licensed path=fast shows text", () => {
  const note = parseMatchAgentNote({
    ok: true,
    live: true,
    text: "Picture HUD labeled Cross — unlabeled pad.",
    ticket_id: "pic-1",
    path: "fast",
    model: "deepseek",
  });
  assert.ok(note);
  assert.equal(note.path, "fast");
  assert.match(note.text, /Picture HUD/);
});

test("does not harvest the evidence bag", () => {
  const note = parseMatchAgentNote({
    match_agent: {
      ok: true,
      live: true,
      text: "Board licensed on this seq.",
      ticket_id: "c1",
      path: "confirm",
      model: "deepseek",
      evidence: { home_score: 99, away_score: 1 },
    },
  });
  assert.ok(note);
  assert.equal("evidence" in note, false);
});
