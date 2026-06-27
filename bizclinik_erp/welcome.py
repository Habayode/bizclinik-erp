"""JARVIS-style welcome shown once when a user signs in.

A sleek animated banner that greets the user by name with a time-aware line and
a short live briefing (pending approvals, critical agent flags), and speaks it
aloud via the browser's Web Speech API. The text-building functions are pure and
testable; render() does the Streamlit/HTML side.
"""
from __future__ import annotations

import datetime
import html as _html
import json
from typing import Optional


def time_greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


def display_name(user: dict) -> str:
    raw = (user or {}).get("full_name") or (user or {}).get("username")
    if not raw:
        return "there"
    first = str(raw).split("@")[0].replace("_", ".").split(".")[0].strip()
    if not first:
        return "there"
    return first[:1].upper() + first[1:]


def build_briefing(session, user: Optional[dict] = None) -> list[str]:
    """Best-effort live status lines. Never raises — a greeting must not break
    login if a query fails."""
    lines: list[str] = []
    try:
        from sqlalchemy import func, select

        from .models import ApprovalRequest, ApprovalStatus
        n = session.execute(
            select(func.count()).select_from(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        ).scalar_one()
        if n:
            lines.append(f"{n} approval{'s' if n != 1 else ''} awaiting a decision")
    except Exception:
        pass
    try:
        from .agents import findings_for_run, latest_run, list_agents
        crit = 0
        for a in list_agents():
            r = latest_run(session, a.key)
            if not r:
                continue
            for f in findings_for_run(session, r.id):
                if f.severity == "critical" and f.status not in ("dismissed", "resolved"):
                    crit += 1
        if crit:
            lines.append(f"{crit} critical item{'s' if crit != 1 else ''} "
                         f"flagged by the agents")
    except Exception:
        pass
    return lines


def subline(briefing: list[str]) -> str:
    if briefing:
        return "Welcome back to Trakit365. You have " + " and ".join(briefing) + "."
    return "Welcome back to Trakit365. Everything is in order."


def spoken_text(greeting: str, name: str, briefing: list[str]) -> str:
    body = ("You have " + " and ".join(briefing) + ". ") if briefing \
        else "Everything is in order. "
    return (f"{greeting}, {name}. Welcome back to Trakit365. {body}"
            "All systems are online. How may I help?")


_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:transparent;font-family:'Segoe UI',system-ui,-apple-system,sans-serif}
.jv{position:relative;display:flex;align-items:center;gap:22px;padding:22px 26px;border-radius:16px;
 background:radial-gradient(120% 140% at 0% 0%,#0b1b3a 0%,#0a142b 55%,#07101f 100%);
 border:1px solid rgba(14,165,164,.45);box-shadow:0 0 0 1px rgba(14,165,164,.12),0 14px 40px rgba(0,0,0,.45);
 overflow:hidden;animation:rise .6s cubic-bezier(.2,.8,.2,1)}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.jv:before{content:"";position:absolute;inset:0;background:linear-gradient(transparent 50%,rgba(14,165,164,.035) 50%);
 background-size:100% 4px;pointer-events:none;opacity:.6}
.ring{flex:0 0 84px;width:84px;height:84px;filter:drop-shadow(0 0 10px rgba(14,165,164,.7))}
.ring svg{width:100%;height:100%}
.r1{transform-origin:50% 50%;animation:spin 6s linear infinite}
.r2{transform-origin:50% 50%;animation:spin 9s linear infinite reverse}
.core{animation:pulse 2.2s ease-in-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:.5}50%{opacity:1}}
.txt{flex:1;min-width:0;color:#e8eefc}
.kic{font-size:.66rem;letter-spacing:.28em;color:#0EA5A4;font-weight:700;text-transform:uppercase;margin-bottom:7px;opacity:.92}
.hl{font-size:1.5rem;font-weight:700;line-height:1.15;white-space:nowrap;overflow:hidden}
.cur{border-right:2px solid #0EA5A4;margin-left:1px;animation:blink 1s steps(1) infinite}
@keyframes blink{50%{border-color:transparent}}
.sb{margin-top:7px;font-size:.95rem;color:#aebbd6;opacity:0;animation:fade .6s ease forwards;animation-delay:1s}
@keyframes fade{to{opacity:1}}
.act{position:absolute;top:12px;right:14px;display:flex;gap:8px}
.btn{cursor:pointer;border:1px solid rgba(14,165,164,.5);background:rgba(14,165,164,.08);color:#bfeae8;
 font-size:.72rem;border-radius:999px;padding:5px 11px;transition:.15s;user-select:none}
.btn:hover{background:rgba(14,165,164,.22)}
.x{border-color:rgba(255,255,255,.18);color:#9fb0cf;background:transparent;padding:5px 9px}
</style></head><body>
<div class="jv" id="jv">
 <div class="act"><span class="btn" id="rep">&#128266; Replay</span><span class="btn x" id="cls">&#10005;</span></div>
 <div class="ring"><svg viewBox="0 0 100 100">
   <circle class="r1" cx="50" cy="50" r="44" fill="none" stroke="#0EA5A4" stroke-width="2" stroke-dasharray="10 8" opacity=".85"/>
   <circle class="r2" cx="50" cy="50" r="34" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="4 10" opacity=".6"/>
   <circle class="core" cx="50" cy="50" r="20" fill="none" stroke="#0EA5A4" stroke-width="6" opacity=".8"/>
   <circle cx="50" cy="50" r="7" fill="#0EA5A4"/></svg></div>
 <div class="txt">
   <div class="kic">Trakit365 &bull; Assistant</div>
   <div class="hl"><span id="hl"></span><span class="cur" id="cur"></span></div>
   <div class="sb">__SUB__</div>
 </div>
</div>
<script>
var HEAD=__HEAD__, SPK=__SPK__;
var el=document.getElementById('hl'),cur=document.getElementById('cur'),i=0;
(function type(){ if(i<=HEAD.length){ el.textContent=HEAD.slice(0,i); i++; setTimeout(type,42); } else { cur.style.display='none'; } })();
function speak(){ try{ if(!window.speechSynthesis) return; window.speechSynthesis.cancel();
  var u=new SpeechSynthesisUtterance(SPK); u.rate=.98; u.pitch=1.0;
  var vs=window.speechSynthesis.getVoices();
  var v=vs.find(function(x){return /en-GB/i.test(x.lang)})||vs.find(function(x){return /Daniel|Arthur|George|UK English Male/i.test(x.name)})||vs.find(function(x){return /^en/i.test(x.lang)})||vs[0];
  if(v) u.voice=v; window.speechSynthesis.speak(u);
}catch(e){} }
function ready(){ if(!window.speechSynthesis) return;
  if(window.speechSynthesis.getVoices().length){ speak(); }
  else { window.speechSynthesis.onvoiceschanged=function(){ window.speechSynthesis.onvoiceschanged=null; speak(); }; } }
setTimeout(ready,350);
document.getElementById('rep').onclick=speak;
document.getElementById('cls').onclick=function(){ try{window.speechSynthesis.cancel();}catch(e){}
  var j=document.getElementById('jv'); j.style.transition='.3s'; j.style.opacity='0'; setTimeout(function(){ j.style.display='none'; },300); };
</script></body></html>"""


def build_html(head: str, sub: str, spoken: str) -> str:
    """Substitute the greeting into the component template (pure / testable)."""
    return (_HTML
            .replace("__SUB__", _html.escape(sub))
            .replace("__HEAD__", json.dumps(head))
            .replace("__SPK__", json.dumps(spoken)))


def render(user: dict, session, *, now: Optional[datetime.datetime] = None) -> None:
    """Render the one-shot welcome banner (Streamlit runtime only)."""
    import streamlit.components.v1 as components

    now = now or datetime.datetime.now()
    greeting = time_greeting(now.hour)
    name = display_name(user)
    try:
        briefing = build_briefing(session, user)
    except Exception:
        briefing = []
    doc = build_html(f"{greeting}, {name}", subline(briefing),
                     spoken_text(greeting, name, briefing))
    components.html(doc, height=216)
