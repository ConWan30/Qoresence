"""MCP server tests — stdio JSON-RPC fallback + in-process glass."""
from __future__ import annotations
import json, subprocess, sys

def _rpc(msgs):
    p = subprocess.Popen([sys.executable, "-m", "qoresence.mcp.server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
    out, _ = p.communicate(inp, timeout=30)
    lines = [json.loads(x) for x in out.strip().splitlines() if x.strip()]
    p.terminate()
    return lines

def test_mcp_initialize_and_tools_list():
    reqs = [{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},{"jsonrpc":"2.0","id":2,"method":"tools/list"}]
    resps = _rpc(reqs)
    assert len(resps)==2
    assert resps[0]["result"]["serverInfo"]["name"]=="qoresence"
    names={t["name"] for t in resps[1]["result"]["tools"]}
    assert names=={"get_snapshot","get_events","get_health","get_frame","export_clip","get_situation"}

def test_mcp_resources_and_prompts_list():
    reqs=[{"jsonrpc":"2.0","id":1,"method":"resources/list"},{"jsonrpc":"2.0","id":2,"method":"prompts/list"}]
    resps=_rpc(reqs)
    assert "snapshot" in str(resps[0]["result"]["resources"])
    assert "coach_clutch" in str(resps[1]["result"]["prompts"])

def test_mcp_tools_call_in_process_snapshot_and_events():
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core import RetinaEventBus, SessionAuthority
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event
    import qoresence.mcp.server as mcp_server
    sess=SessionAuthority.mint()
    bus=RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g=AgentGlass(bus=bus, session_identity=sess)
    g.start()
    for i in range(3):
        bus.emit(make_event(sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"i":i}))
    import time; time.sleep(0.05)
    orig=mcp_server._get_glass
    try:
        mcp_server._get_glass=lambda: g
        snap=mcp_server.handle_get_snapshot()
        assert snap["ok"] is True and snap["seq"]>=3
        ev=mcp_server.handle_get_events(since=0, limit=2)
        assert ev["count"]==2 and ev["next_seq"]>=3
        health=mcp_server.handle_get_health()
        assert health["ok"] is True and "seq" in health
        situ=mcp_server.handle_get_situation()
        assert situ["ok"] is True and "coupling" in situ
    finally:
        mcp_server._get_glass=orig
        g.stop()

def test_mcp_export_clip_and_unknown():
    reqs=[{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"export_clip","arguments":{"seconds":5}}},{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_situation","arguments":{}}},{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"unknown_tool","arguments":{}}}]
    resps=_rpc(reqs)
    assert resps[0]["result"]["content"][0]["type"]=="text"
    assert resps[1]["result"]["content"][0]["type"]=="text"
    assert resps[2]["error"]["code"]==-32601

def test_mcp_notifications_and_resources_read():
    reqs=[{"jsonrpc":"2.0","id":1,"method":"ping"},{"jsonrpc":"2.0","method":"notifications/initialized","params":{}},{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"uri":"qoresence://snapshot"}},{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"coach_clutch"}}]
    resps=_rpc(reqs)
    assert len(resps)==3
    assert resps[0]["result"]=={}
    assert "contents" in resps[1]["result"]

def test_mcp_tools_call_http_unreachable_hint():
    import qoresence.mcp.server as mcp_server
    orig=mcp_server._get_glass
    try:
        mcp_server._get_glass=lambda: None
        health=mcp_server.handle_get_health()
        assert health.get("error")=="http_unreachable"
        assert "agent-glass" in health.get("hint","").lower() or "refused" in health.get("hint","").lower()
        reqs=[{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_health","arguments":{}}},{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_snapshot","arguments":{}}}]
        resps=_rpc(reqs)
        for r in resps:
            txt=r["result"]["content"][0]["text"]
            obj=json.loads(txt)
            assert obj.get("error")=="http_unreachable" or obj.get("ok") is False
    finally:
        mcp_server._get_glass=orig
