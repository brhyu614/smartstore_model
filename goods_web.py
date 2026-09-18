#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
상세페이지 이미지 만들기 · 웹 화면
==================================
goods_shot.py 를 브라우저에서 쓰는 버전입니다. 같은 폴더에 두 파일이 함께 있어야 합니다.

실행
----
    cd ~/Downloads
    export OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
    python3 goods_web.py

브라우저가 자동으로 열립니다 (http://127.0.0.1:8765).
사진을 끌어다 놓고 제품명·모델을 고른 뒤 [① 대표컷 만들기] 를 누르세요.
대표컷이 마음에 들면 [이 모델로 나머지 5컷] 을 누릅니다.

결과는 이 스크립트가 있는 폴더의 생성결과/<제품명>/ 에 저장됩니다.
두 파일을 통째로 다른 곳에 옮겨도 그대로 동작하고, 저장 위치도 함께 따라갑니다.
다른 곳에 저장하려면  python3 goods_web.py --outdir ~/어디든/폴더
내 컴퓨터에서만 열리며, API 키는 브라우저로 나가지 않습니다.
"""

import argparse
import base64
import hashlib
import hmac
import io
import json
import os
import re
import sys
import threading
import urllib.parse
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import goods_shot as gs
except ImportError:
    sys.exit("goods_shot.py 를 찾지 못했습니다. 두 파일을 같은 폴더에 두고 실행하세요.")
try:
    import chat_agent as ca
except ImportError:
    ca = None            # 없어도 화면은 그대로 돌아간다. 대화창만 안 뜬다.

JOBS = {}
LOCK = threading.Lock()
HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "생성결과")   # 스크립트 옆에 저장 → 폴더째 옮겨도 따라간다
MODEL = "google/gemini-3-pro-image"
SIZE = "1K"
REST = ["wear", "side", "close", "detail", "thumb"]

# ------------------------------------------------------- 팀 공용 배포 설정
# 모두 환경변수로 켠다. APP_PASSWORD 가 비어 있으면 예전처럼 "내 컴퓨터 전용" 모드.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
APP_SECRET = os.environ.get("APP_SECRET", "").strip() or \
    base64.b64encode(os.urandom(24)).decode()
COOKIE = "gsauth"
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12") or 12)
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "0") or 0)   # 하루 생성 장수, 0=무제한
MAX_JOBS = int(os.environ.get("MAX_JOBS", "12") or 12)       # 메모리에 남겨 둘 작업 수

USED = {"day": "", "n": 0}
FAILS = {}          # 로그인 실패 기록 {아이피: [횟수, 잠금해제시각]}


def need_auth():
    return bool(APP_PASSWORD)


def make_token():
    exp = str(int(time.time()) + SESSION_HOURS * 3600)
    sig = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()[:32]
    return exp + "." + sig


def token_ok(tok):
    try:
        exp, sig = (tok or "").split(".", 1)
        want = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(sig, want) and int(exp) > time.time()
    except Exception:
        return False


def locked_out(ip):
    c = FAILS.get(ip)
    return bool(c and c[1] > time.time())


def note_login(ip, ok):
    if ok:
        FAILS.pop(ip, None)
        return
    c = FAILS.setdefault(ip, [0, 0])
    c[0] += 1
    if c[0] >= 5:                      # 5번 틀리면 5분 잠금
        c[0], c[1] = 0, time.time() + 300


def quota_state():
    today = time.strftime("%Y-%m-%d")
    if USED["day"] != today:
        USED.update(day=today, n=0)
    left = max(0, DAILY_LIMIT - USED["n"]) if DAILY_LIMIT > 0 else -1
    return {"limit": DAILY_LIMIT, "used": USED["n"], "left": left}


def quota_take():
    """생성 1장 차감. 한도를 넘으면 False."""
    if DAILY_LIMIT <= 0:
        return True
    with LOCK:
        quota_state()
        if USED["n"] >= DAILY_LIMIT:
            return False
        USED["n"] += 1
        return True


def quota_give_back():
    if DAILY_LIMIT > 0:
        with LOCK:
            USED["n"] = max(0, USED["n"] - 1)


def evict_jobs():
    """오래된 작업을 메모리에서 비운다 (클라우드 메모리 보호)."""
    with LOCK:
        if len(JOBS) <= MAX_JOBS:
            return
        old = sorted(JOBS.items(), key=lambda kv: kv[1].get("at", 0))
        for jid, _ in old[:len(JOBS) - MAX_JOBS]:
            JOBS.pop(jid, None)


# ----------------------------------------------------------------- 작업
def norm_extras(extras):
    """추가 사진을 [{'view':종류,'url':데이터URL}] 로 통일한다 (옛 형식인 문자열도 허용)."""
    out = []
    for e in (extras or []):
        if isinstance(e, dict):
            url, view = e.get("url") or "", (e.get("view") or "").strip()
        else:
            url, view = e, ""
        if not (isinstance(url, str) and url.startswith("data:image/")):
            continue
        out.append({"view": view if view in gs.VIEWS else "기타", "url": url})
    return out[:6]


def new_job(name, who, garment_dataurl, extras=None, graphic=False,
            kind="", styling=None):
    jid = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[jid] = {
            "id": jid, "name": name, "who": who,
            "garment": garment_dataurl,
            "extras": norm_extras(extras), "graphic": bool(graphic),
            "kind": kind or gs.guess_kind(name), "styling": styling or {},
            "poses": {}, "plan": list(REST),
            "cuts": {c: {"state": "idle", "err": "", "n": 0} for c in gs.CUTS},
            "bytes": {}, "outdir": os.path.join(OUTDIR, gs.safe_dir(name)),
            "at": time.time(),
        }
    evict_jobs()
    return jid


def _save_source(job):
    """올린 옷 사진 원본을 결과 폴더에 함께 남긴다 (나중에 다시 뽑을 때 필요)."""
    if job.get("_src_saved"):
        return
    def put(dataurl, stem):
        raw = (dataurl or "").split(",", 1)
        if len(raw) != 2:
            return
        blob = base64.b64decode(raw[1])
        with open(os.path.join(job["outdir"], stem + gs.ext_for(blob)), "wb") as f:
            f.write(blob)
    try:
        put(job.get("garment"), "_원본")
        for i, e in enumerate(job.get("extras") or [], 1):
            put(e["url"], "_원본_%d_%s" % (i, e["view"]))
        job["_src_saved"] = True
    except Exception:
        job["_src_saved"] = True


def run_cut(job, cut):
    """컷 하나 생성. 실패하면 상태에 남긴다."""
    c = job["cuts"][cut]
    c["state"] = "running"; c["err"] = ""
    if not quota_take():
        c["state"] = "error"
        c["err"] = ("오늘 만들 수 있는 장수(%d장)를 다 썼습니다. "
                    "내일 다시 시도하거나 관리자에게 한도를 올려 달라고 하세요." % DAILY_LIMIT)
        return
    try:
        refs = [job["garment"]]
        if cut in ("wear", "side", "close"):
            hero = job["bytes"].get("hero")
            if not hero:
                raise RuntimeError("대표컷이 먼저 있어야 합니다.")
            refs.append(gs.data_url(hero))
        two = len(refs) == 2
        extras = job.get("extras") or []
        refs += [e["url"] for e in extras]
        prompt = gs.build_prompt(cut, gs.clean(job["name"]),
                                 gs.model_desc(job["who"]), two,
                                 graphic=job.get("graphic"),
                                 extras=[e["view"] for e in extras],
                                 pose=(job.get("poses") or {}).get(cut),
                                 styling=job.get("styling"), kind=job.get("kind"))
        blob = gs.generate(prompt, refs, gs.ASPECT[cut], SIZE, MODEL)
        job["bytes"][cut] = blob
        try:
            # 클라우드에서는 디스크가 임시라 실패해도 무시한다 (내려받기로 가져간다)
            os.makedirs(job["outdir"], exist_ok=True)
            _save_source(job)
            with open(os.path.join(job["outdir"], cut + gs.ext_for(blob)), "wb") as f:
                f.write(blob)
        except OSError:
            pass
        c["n"] += 1
        c["state"] = "done"
    except Exception as e:
        quota_give_back()
        c["state"] = "error"
        c["err"] = str(e)[:400]


def run_hero(jid, who=None):
    job = JOBS[jid]
    if who is not None:
        job["who"] = who
    # 대표컷을 새로 뽑으면 인물이 걸린 컷들은 무효가 된다
    for c in ("wear", "side", "close"):
        job["cuts"][c] = {"state": "idle", "err": "", "n": 0}
        job["bytes"].pop(c, None)
    run_cut(job, "hero")


def run_one(jid, cut):
    run_cut(JOBS[jid], cut)


def run_rest(jid):
    job = JOBS[jid]
    for cut in (job.get("plan") or REST):
        if job["cuts"][cut]["state"] == "done":
            continue
        run_cut(job, cut)
        if job["cuts"][cut]["state"] == "error":
            break


def apply_look(job, b):
    """다시 뽑기 요청에 코디·제품 종류가 함께 왔으면 작업에 반영한다."""
    if isinstance(b.get("styling"), dict):
        job["styling"] = b["styling"]
    if b.get("kind"):
        job["kind"] = b["kind"]


def spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ----------------------------------------------------------------- 화면
LOGIN = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>상세페이지 이미지 만들기 · 로그인</title>
<style>
@font-face{font-family:"Pretendard";src:url("/pretendard.woff2") format("woff2");
 font-weight:400 700;font-style:normal;font-display:swap}
:root{--bg:#f4f6fb;--fg:#141a2e;--dim:#6b7488;--card:#fff;--line:#e4e9f2;
      --acc:#4b62ed;--acc2:#9660ee;--accsoft:#edeffe;--bad:#e11d48;
      color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0b0e18;--fg:#e7ebf4;--dim:#949db4;
      --card:#141926;--line:#232a3b;--acc:#7c8cf8;--acc2:#b47cf5;--accsoft:#1b2142;
      --bad:#fb7185}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:var(--bg);color:var(--fg);padding:24px;
 font:15px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.box{width:100%;max-width:360px;background:var(--card);border:1px solid var(--line);
 border-radius:16px;padding:30px 26px}
h1{font-size:19px;margin:0 0 6px}
p{color:var(--dim);font-size:13px;margin:0 0 20px}
input{width:100%;padding:12px 13px;border:1px solid var(--line);border-radius:10px;
 background:var(--bg);color:var(--fg);font:15px/1 inherit}
button{width:100%;margin-top:12px;padding:12px;border:0;border-radius:10px;
 background:var(--acc);color:#fff;font:600 15px/1 inherit;cursor:pointer}
.err{color:var(--bad);font-size:13px;margin-top:12px;min-height:18px}
</style></head><body>
<form class="box" id="f">
  <h1>상세페이지 이미지 만들기</h1>
  <p>팀 공용 비밀번호를 넣어주세요.</p>
  <input type="password" id="pw" autocomplete="current-password" autofocus placeholder="비밀번호">
  <button type="submit">들어가기</button>
  <div class="err" id="e"></div>
</form>
<script>
document.getElementById("f").onsubmit=async ev=>{
  ev.preventDefault();
  const e=document.getElementById("e"); e.textContent="";
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({pw:document.getElementById("pw").value})});
  const j=await r.json();
  if(j.ok) location.href="/"; else e.textContent=j.error||"들어가지 못했습니다.";
};
</script></body></html>"""

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>상세페이지 이미지 만들기</title>
<style>
@font-face{font-family:"Pretendard";src:url("/pretendard.woff2") format("woff2");
 font-weight:400 700;font-style:normal;font-display:swap}
:root{--bg:#f4f6fb;--fg:#141a2e;--dim:#6b7488;--card:#fff;--line:#e4e9f2;
      --acc:#4b62ed;--acc2:#9660ee;--accsoft:#edeffe;--bad:#e11d48;--soft:#edf0f7;
      color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0b0e18;--fg:#e7ebf4;--dim:#949db4;
      --card:#141926;--line:#232a3b;--acc:#7c8cf8;--acc2:#b47cf5;--accsoft:#1b2142;
      --bad:#fb7185;--soft:#141926}}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--fg);
 font:15px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.wrap{max-width:1060px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px}
label{display:block;font-size:12px;color:var(--dim);margin:0 0 5px;font-weight:600}
input,select,textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:10px;
 background:transparent;color:inherit;font:inherit}
select{font-size:14px}
textarea{min-height:64px;resize:vertical}
.traits{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:820px){.traits{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.traits{grid-template-columns:1fr}}
.wide{grid-column:1/-1}
.field{margin-bottom:14px}
details.grp{border:1px solid var(--line);border-radius:12px;margin-bottom:10px;background:var(--card)}
details.grp>summary{cursor:pointer;padding:11px 14px;font:600 12.5px/1.4 inherit;
 color:var(--dim);letter-spacing:.03em;list-style:none}
details.grp>summary::-webkit-details-marker{display:none}
details.grp>summary::before{content:"▸ ";color:var(--acc)}
details.grp[open]>summary::before{content:"▾ "}
details.grp>div{padding:4px 14px 16px}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{display:inline-flex;align-items:center;gap:5px;padding:6px 10px;border:1px solid var(--line);
 border-radius:999px;font-size:12.5px;cursor:pointer;color:var(--fg);margin:0}
.chip input{width:auto;margin:0}
.chip:has(input:checked){border-color:var(--acc);color:var(--acc)}
details.fine{border:0;border-bottom:1px solid var(--line);border-radius:0;margin:0;background:transparent}
details.fine>summary{padding:8px 12px 10px 40px;font-size:12px}
details.fine>div{padding:0 12px 14px 40px}
.finegrp{margin-bottom:12px}
.finegrp>label{font-size:11.5px;letter-spacing:.04em;color:var(--acc)}
.plan .traits{gap:8px}
.plan{border:1px solid var(--line);border-radius:12px;overflow:hidden}
.planrow{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line)}
.planrow:last-child{border-bottom:0}
.planrow input[type=checkbox]{width:auto;margin:0}
.planrow span{font-size:13px;min-width:86px}
.planrow select{flex:1;padding:6px 9px;font-size:13px}
.saved{border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:18px;background:var(--soft)}
.savedrow{display:flex;gap:8px;align-items:center}
.savedrow select,.savedrow input{flex:1;min-width:0}
.savedrow button{white-space:nowrap}
#mthumb img{height:110px;border-radius:8px;border:1px solid var(--line);margin-top:10px;display:block}
.where{font-size:12.5px;color:var(--dim);background:var(--soft);border:1px solid var(--line);
 border-radius:10px;padding:10px 13px;margin-bottom:20px;word-break:break-all}
.where b{color:var(--fg);font-weight:600}
.prev{margin-top:12px;padding:11px 13px;background:var(--soft);border-radius:10px;
 font-size:12.5px;color:var(--dim);line-height:1.55;border:1px solid var(--line)}
.togg{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--dim);
 margin-top:12px;cursor:pointer;user-select:none}
.togg input{width:auto}
#drop{border:2px dashed var(--line);border-radius:14px;padding:26px;text-align:center;
 color:var(--dim);cursor:pointer;font-size:14px}
#drop.on{border-color:var(--acc);color:var(--acc)}
#drop img{max-height:180px;border-radius:10px;display:block;margin:0 auto 8px}
#drop2{border:2px dashed var(--line);border-radius:12px;padding:18px;text-align:center;
 color:var(--dim);cursor:pointer;font-size:13.5px}
#drop2.on{border-color:var(--acc);color:var(--acc)}
.thumbs{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.thumbs figure{margin:0;position:relative;width:92px}
.thumbs img{height:72px;width:92px;object-fit:cover;border-radius:8px;
 border:1px solid var(--line);display:block}
.thumbs select{margin-top:5px;padding:4px 6px;font-size:11.5px;width:100%}
.thumbs button{position:absolute;top:-6px;right:-6px;width:20px;height:20px;padding:0;
 border-radius:50%;font:700 12px/1 inherit;background:var(--bad)}
button{padding:11px 20px;border:0;border-radius:10px;color:#fff;cursor:pointer;
 background:linear-gradient(135deg,var(--acc),var(--acc2));font:600 14px/1 inherit}
button:hover{filter:brightness(1.06)}
button.ghost{background:transparent;color:var(--fg);border:1px solid var(--line)}
button.mini{padding:6px 12px;font-size:12.5px}
button:disabled{opacity:.45;cursor:default}
.btns{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
.hero{display:grid;grid-template-columns:290px 1fr;gap:22px;align-items:start}
@media(max-width:820px){.hero{grid-template-columns:1fr}}
.hero img{width:100%;border-radius:12px;border:1px solid var(--line);display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(186px,1fr));gap:14px;margin-top:6px}
.tile{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--card);
 display:flex;flex-direction:column}
/* 컷마다 비율이 달라도(2:3, 1:1) 칸 높이는 같게. 잘라내지 않고 안에 맞춘다 */
.tile .shot{aspect-ratio:4/5;background:var(--soft);display:flex;align-items:center;
 justify-content:center;overflow:hidden}
.tile .shot img{max-width:100%;max-height:100%;width:auto;height:auto;display:block}
.tile .ph{color:var(--dim);font-size:12.5px;text-align:center;padding:10px}
.tile .cap{padding:9px 11px 10px;border-top:1px solid var(--line);margin-top:auto}
.tile .cap b{display:block;font-size:12.5px;font-weight:600;color:var(--fg);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .capr{display:flex;gap:7px;align-items:center;margin-top:6px}
.tile a{color:var(--acc);text-decoration:none;font-size:11.5px;white-space:nowrap}
.tile .re{padding:3px 10px;font-size:11.5px;background:transparent;color:var(--acc);
 border:1px solid var(--line);border-radius:999px;white-space:nowrap;margin-left:auto}
.err{color:var(--bad);font-size:13px;margin-top:10px;white-space:pre-wrap;word-break:break-word}
.note{color:var(--dim);font-size:12.5px;margin-top:12px}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--line);
 border-top-color:var(--acc);border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
/* 대화 입력기 — 화면을 대체하지 않고 화면을 채운다 */
#chatbar{position:fixed;left:0;right:0;bottom:0;z-index:50;background:var(--card);
 border-top:1px solid var(--line);box-shadow:0 -6px 24px rgba(0,0,0,.07)}
#chatbar .cwrap{max-width:1000px;margin:0 auto;padding:12px 18px 10px}
#chatbar .crow{display:flex;gap:8px;align-items:center}
#chatbar input{flex:1;padding:11px 13px;font-size:14px}
#chatbar .chint{font-size:11.5px;color:var(--dim);margin-top:6px}
#chatopen{position:fixed;right:20px;bottom:20px;z-index:51;border-radius:999px;
 padding:12px 20px;font-size:13.5px;box-shadow:0 6px 20px rgba(0,0,0,.2)}
body.chaton{padding-bottom:128px}
#chatlog{max-height:min(210px,32vh);overflow-y:auto;margin-bottom:10px;padding-right:4px}
#chatlog .m{margin-bottom:8px;font-size:13px;line-height:1.5}
#chatlog .me{text-align:right}
#chatlog .me span{display:inline-block;background:var(--acc);color:#fff;
 padding:7px 12px;border-radius:14px 14px 4px 14px;max-width:78%;text-align:left}
#chatlog .ai span{display:inline-block;background:var(--soft);color:var(--fg);
 padding:7px 12px;border-radius:14px 14px 14px 4px;max-width:85%;
 border:1px solid var(--line)}
#chatlog .ai.bad span{color:var(--bad)}
#chatlog .ask span{display:flex;gap:7px;align-items:center;flex-wrap:wrap}
#chatlog .ask button{padding:5px 12px;font-size:12px;border-radius:999px}
/* 눌러서 고르는 칩 — 타이핑과 스크롤을 줄인다 */
#chatlog .krow{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;max-width:88%}
.kchip{display:inline-flex;align-items:center;gap:6px;max-width:100%;
 padding:4px 11px;border-radius:999px;cursor:pointer;
 font:500 11.5px/1.6 inherit;border:1px solid var(--line);
 background:var(--card);color:var(--fg)}
.kchip:hover{border-color:var(--acc)}
.kchip i{font-style:normal;color:var(--dim);flex:0 0 auto}
.kchip b{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kchip.set{background:var(--accsoft);border-color:transparent}
.kchip.undo{color:var(--dim);background:transparent}
#quick{display:flex;gap:6px;overflow-x:auto;padding:0 0 9px;scrollbar-width:none}
#quick::-webkit-scrollbar{display:none}
#quick .qlab{flex:0 0 auto;align-self:center;font-size:11.5px;color:var(--dim);margin-right:2px}
#quick .kchip{flex:0 0 auto;background:var(--accsoft);border-color:transparent;
 color:var(--acc);font-weight:600}
#quick .kchip:hover{background:var(--acc);color:#fff}
/* 여러 개 고르는 칸의 소그룹 제목 */
.chips .gsep{flex:0 0 100%;font-size:11px;color:var(--dim);margin:4px 0 -2px}
.chips .gsep:first-child{margin-top:0}
/* 코디 한 칸: 대분류 → 아이템 → 속성 */
.slot{grid-column:1/-1;border-top:1px solid var(--line);padding-top:11px}
.slot:first-of-type{border-top:0;padding-top:0}
.srow{display:flex;gap:8px;align-items:center}
.srow select{min-width:0}
.srow .cat{flex:0 0 clamp(110px,26%,168px);background:var(--soft);color:var(--dim);font-size:13px}
.srow .item{flex:1 1 auto;font-weight:500}
.arow{display:flex;flex-wrap:wrap;gap:7px 10px;margin-top:8px}
.arow .ax{display:flex;align-items:center;gap:5px}
.arow em{font-style:normal;font-size:11.5px;color:var(--dim)}
.arow select{width:auto;min-width:84px;padding:6px 9px;font-size:12.5px;border-radius:8px}
@media(max-width:620px){.srow{flex-wrap:wrap}.srow .cat,.srow .item{flex:1 1 100%}}
@keyframes ping{0%{box-shadow:0 0 0 0 var(--acc)}100%{box-shadow:0 0 0 9px transparent}}
.ping{animation:ping .9s ease-out;border-radius:10px}
@keyframes flash{0%{background:var(--acc);color:#fff}100%{background:transparent}}
.justset{animation:flash 1.1s ease-out}
.look{margin-top:16px}
.look>summary{font-weight:600;font-size:13.5px}
.look .sum{font-weight:400;color:var(--dim);font-size:12.5px;margin-left:6px}
.hide{display:none!important}
code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;background:var(--line);padding:2px 6px;border-radius:5px}
</style></head><body><div class="wrap">

<h1>상세페이지 이미지 만들기</h1>
<div class="sub">옷 사진 한 장 → 모델을 항목별로 지정 → 대표컷 확인 → 나머지 5컷</div>
<div class="where" id="where">저장 위치를 확인하는 중…</div>

<div class="card" id="step1">
  <div class="field">
    <label>옷 사진 (대표 · 앞면)</label>
    <div id="drop">여기로 사진을 끌어다 놓거나 눌러서 고르세요<br><span style="font-size:12px">jpg · png · webp</span></div>
    <input type="file" id="file" accept="image/*" class="hide">
  </div>
  <div class="field"><label>제품명</label>
    <input id="name" placeholder="예: 하늘색 립업 후드티"></div>

  <div class="field">
    <label>옷 사진 추가 <span style="font-weight:400;color:var(--dim)">— 뒷면 · 옆면 · 디테일 등 (선택, 최대 6장)</span></label>
    <div id="drop2">여기로 사진을 끌어다 놓거나 눌러서 고르세요 (여러 장 한 번에)<br>
      <span style="font-size:12px">뒷면 사진을 넣으면 측면·착용컷에서 뒤태를 지어내지 않습니다</span></div>
    <input type="file" id="file2" accept="image/*" multiple class="hide">
    <div id="thumbs" class="thumbs"></div>
    <label class="togg"><input type="checkbox" id="gfx">
      프린트·로고가 있는 옷입니다 <span style="color:var(--dim)">(그래픽을 그대로 재현)</span></label>
  </div>

  <details class="grp look" id="lookA">
    <summary>코디 — 제품 말고 함께 입는 것 <span class="sum" id="sumA"></span></summary>
    <div class="field" style="margin:12px 0 0">
      <label>제품 종류 <span style="font-weight:400;color:var(--dim)">— 제품명으로 자동으로 잡습니다. 틀리면 고쳐 주세요</span></label>
      <select id="kindA"></select>
    </div>
    <div id="sA"></div>
  </details>

  <div class="saved">
    <label>저장된 모델</label>
    <div class="savedrow">
      <select id="mlist"><option value="">— 저장된 모델 없음 —</option></select>
      <button class="ghost mini" id="mload">불러오기</button>
      <button class="ghost mini" id="mdel">삭제</button>
    </div>
    <div class="savedrow" style="margin-top:8px">
      <input id="mname" placeholder="이 조합에 이름 붙이기 (예: 우리몰 기본모델)">
      <button class="ghost mini" id="msave">현재 설정 저장</button>
    </div>
    <div id="mthumb"></div>
  </div>

  <label style="margin-top:18px">모델 만들기 <span style="font-weight:400">— 지정하지 않은 항목은 프롬프트에 넣지 않습니다</span></label>
  <div id="tA"></div>
  <div class="btns" style="margin-top:4px">
    <button class="ghost mini" id="resetA">전부 지정 안 함으로</button>
    <button class="ghost mini" id="openA">모든 그룹 펼치기</button>
  </div>
  <label class="togg"><input type="checkbox" id="cAchk"> 대신 영어로 직접 묘사할게요</label>
  <textarea id="cA" class="hide" style="margin-top:8px"
    placeholder="a Korean female model in her early 20s with a short bob, sporty build"></textarea>
  <div class="prev" id="pA">…</div>

  <div class="btns"><button id="go">① 대표컷 만들기</button>
    <span class="note" style="margin:0">한 컷만 먼저 만들어 봅니다</span></div>
  <div class="err hide" id="err1"></div>
</div>

<div class="card hide" id="step2">
  <div class="hero">
    <div id="heroBox"><div class="ph" style="aspect-ratio:2/3;display:flex;align-items:center;
      justify-content:center;border:1px solid var(--line);border-radius:12px;color:var(--dim)">
      <span><span class="spin"></span>만드는 중…</span></div></div>
    <div>
      <label>① 대표컷</label>
      <div class="note" style="margin-top:0">이 인물로 나머지 컷을 이어갑니다. 마음에 드시나요?</div>
      <label style="margin-top:16px">바꿔서 다시 뽑기</label>
      <div id="tB"></div>
      <label class="togg"><input type="checkbox" id="cBchk"> 대신 영어로 직접 묘사할게요</label>
      <textarea id="cB" class="hide" style="margin-top:8px"></textarea>
      <div class="prev" id="pB">…</div>

      <details class="grp look" id="lookB">
        <summary>코디 <span class="sum" id="sumB"></span></summary>
        <div class="field" style="margin:12px 0 0">
          <label>제품 종류</label><select id="kindB"></select>
        </div>
        <div id="sB"></div>
        <div class="note" style="margin-top:10px">코디를 바꾸면 <b>대표컷부터 다시</b> 뽑아야
          나머지 컷에 반영됩니다. 아래 [이 모델로 나머지 컷] 대신 [모델 바꿔서 다시]를 누르세요.</div>
      </details>

      <label style="margin-top:18px">만들 컷과 포즈 고르기</label>
      <div id="plan" class="plan"></div>
      <div class="btns">
        <button id="ok">선택한 컷 만들기</button>
        <button id="again" class="ghost">다시 뽑기</button>
      </div>
      <div class="savedrow" style="margin-top:12px">
        <input id="mname2" placeholder="이 인물 저장하기 (대표컷도 같이 보관)">
        <button class="ghost mini" id="msave2">모델 저장</button>
      </div>
      <div class="note">대표컷을 다시 뽑으면 착용컷 ②③④도 새로 만듭니다.
        디테일·썸네일은 제품만 나와서 인물과 무관합니다.</div>
      <div class="err hide" id="err2"></div>
    </div>
  </div>
</div>

<div class="card hide" id="step3">
  <label>전체 컷</label>
  <div class="grid" id="grid"></div>
  <div class="note" id="saved"></div>
  <div class="btns">
    <a id="zip" class="hide" href="#" download><button type="button">전체 내려받기 (zip)</button></a>
    <button id="reset" class="ghost">새 상품 시작</button></div>
</div>

</div>

<div id="chatbar" class="hide">
  <div class="cwrap">
    <div id="chatlog" class="hide"></div>
    <div id="quick"></div>
    <div class="crow">
      <button id="chattoggle" class="ghost mini" title="대화 내역 보기">💬</button>
      <input id="chatin" placeholder="말로 바꿔 보세요 — 예: 20대 초반 여성, 청순하게. 하의는 검정 슬랙스">
      <button id="chatgo">보내기</button>
      <button id="chatclose" class="ghost mini" title="채팅 닫기">✕</button>
    </div>
    <div class="chint" id="chint">고른 내용은 위 화면에 그대로 채워집니다. 확인하고 고치세요.</div>
  </div>
</div>
<button id="chatopen" class="hide" title="대화로 설정하기">💬 대화로 설정</button>
<script>
const $=i=>document.getElementById(i);
const LABEL={hero:"① 대표컷",wear:"② 정면 착용",side:"③ 측면 착용",
             close:"④ 상반신",detail:"⑤ 원단 디테일",thumb:"⑥ 썸네일"};
const ORDER=["hero","wear","side","close","detail","thumb"];
let img=null, job=null, timer=null, G=[], extras=[];
const esc=t=>String(t).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// ---------- 모델 만들기 패널
function ctl(P,it){
  const id=P+"-"+it.key;
  if(it.type==="text")
    return `<div><label>${esc(it.label)}</label>
      <input id="${id}" data-k="${it.key}" data-t="text" placeholder="${esc(it.ph||"")}"></div>`;
  // 소분류(optgroups)가 있으면 갈래별로 묶어서 보여준다 — 고를 때 덜 헷갈린다
  const gs=(it.optgroups&&it.optgroups.length)?it.optgroups:[{title:"",options:it.options}];
  const box=o=>`<label class="chip"><input type="checkbox" value="${esc(o)}">${esc(o)}</label>`;
  if(it.type==="multi")
    return `<div class="wide"><label>${esc(it.label)}</label>
      <div class="chips" id="${id}" data-k="${it.key}" data-t="multi">
        ${gs.map(g=>(g.title?`<div class="gsep">${esc(g.title)}</div>`:"")
                    +g.options.map(box).join("")).join("")}
      </div></div>`;
  const opt=o=>`<option${o===it.default?" selected":""}>${esc(o)}</option>`;
  return `<div><label>${esc(it.label)}</label>
    <select id="${id}" data-k="${it.key}" data-t="select">
      ${gs.map(g=>g.title
          ? `<optgroup label="${esc(g.title)}">${g.options.map(opt).join("")}</optgroup>`
          : g.options.map(opt).join("")).join("")}
    </select></div>`;
}
function build(P,host){
  host.innerHTML=G.map((g,i)=>
    `<details class="grp"${i===0?" open":""}><summary>${esc(g.title)}</summary>
       <div class="traits">${g.items.map(it=>ctl(P,it)).join("")}</div></details>`).join("");
  host.querySelectorAll("select,input").forEach(el=>{
    const ev = el.tagName==="SELECT"||el.type==="checkbox" ? "change" : "input";
    el.addEventListener(ev,()=>preview(P));
  });
}
function pick(P){
  const chk=$( P==="tA"?"cAchk":"cBchk"), txt=$(P==="tA"?"cA":"cB");
  if(chk.checked) return txt.value.trim() || null;
  const o={};
  G.forEach(g=>g.items.forEach(it=>{
    const el=$(P+"-"+it.key); if(!el)return;
    if(it.type==="multi"){
      const v=[...el.querySelectorAll("input:checked")].map(c=>c.value);
      if(v.length)o[it.key]=v;
    }else{
      const v=el.value.trim();
      if(v && v!=="지정 안 함")o[it.key]=v;
    }
  }));
  return o;
}
let ptimer=null;
function preview(P){
  clearTimeout(ptimer);
  ptimer=setTimeout(async()=>{
    const box=$(P==="tA"?"pA":"pB"), who=pick(P);
    if(who===null){box.textContent="영어 묘사를 적어주세요.";return;}
    const r=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({who})});
    box.textContent=(await r.json()).desc;
  },250);
}
for(const [chk,txt,P] of [["cAchk","cA","tA"],["cBchk","cB","tB"]]){
  $(chk).onchange=()=>{
    $(txt).classList.toggle("hide",!$(chk).checked);
    $(P).classList.toggle("hide",$(chk).checked);
    preview(P);
  };
  $(txt).oninput=()=>preview(P);
}
$("resetA").onclick=()=>{
  G.forEach(g=>g.items.forEach(it=>{
    const el=$("tA-"+it.key); if(!el)return;
    if(it.type==="multi") el.querySelectorAll("input").forEach(c=>c.checked=false);
    else if(it.type==="text") el.value="";
    else el.value = it.key==="sex" ? it.default : "지정 안 함";
  }));
  preview("tA");
};
$("openA").onclick=()=>{
  const all=[...$("tA").querySelectorAll("details")];
  const open=all.every(d=>d.open);
  all.forEach(d=>d.open=!open);
  $("openA").textContent = open ? "모든 그룹 펼치기" : "모든 그룹 접기";
};

// ---------- 저장된 모델
let SAVED=[];
function refreshSaved(sel){
  return fetch("/api/models").then(r=>r.json()).then(list=>{
    SAVED=list;
    $("mlist").innerHTML = list.length
      ? list.map(m=>`<option>${esc(m.name)}</option>`).join("")
      : `<option value="">— 저장된 모델 없음 —</option>`;
    if(sel && list.some(m=>m.name===sel)) $("mlist").value=sel;
    showThumb();
  });
}
function showThumb(){
  const n=$("mlist").value, m=SAVED.find(x=>x.name===n);
  $("mthumb").innerHTML = (m&&m.thumb) ? `<img src="/mthumb/${encodeURIComponent(n)}">` : "";
}
$("mlist").onchange=showThumb;
$("mload").onclick=()=>{
  const n=$("mlist").value; if(!n)return;
  fetch("/api/models").then(r=>r.json()).then(async list=>{
    const m=list.find(x=>x.name===n); if(!m)return;
    const r=await fetch("/api/model_get?name="+encodeURIComponent(n));
    const got=await r.json(), who=got.who;
    setLook("sA",got.styling,true);
    if(typeof who==="string"){ $("cAchk").checked=true; $("cA").value=who;
      $("cA").classList.remove("hide"); $("tA").classList.add("hide"); preview("tA"); return; }
    $("cAchk").checked=false; $("cA").classList.add("hide"); $("tA").classList.remove("hide");
    G.forEach(g=>g.items.forEach(it=>{
      const el=$("tA-"+it.key); if(!el)return;
      const v=who[it.key];
      if(it.type==="multi"){
        const on=Array.isArray(v)?v:[];
        el.querySelectorAll("input").forEach(c=>c.checked=on.includes(c.value));
      }else if(it.type==="text") el.value=v||"";
      else el.value = v || (it.key==="sex"?it.default:"지정 안 함");
    }));
    preview("tA");
  });
};
$("mdel").onclick=async()=>{
  const n=$("mlist").value; if(!n)return;
  if(!confirm("'"+n+"' 을 삭제할까요?"))return;
  await fetch("/api/model_delete",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:n})});
  refreshSaved();
};
async function doSave(nameEl, who, jobId){
  const name=$(nameEl).value.trim();
  if(!name){alert("이름을 적어주세요.");return;}
  const r=await fetch("/api/model_save",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name,who,job:jobId||null,
      styling:pickLook(jobId?"sB":"sA").styling})});
  const j=await r.json();
  if(!j.ok){alert(j.error||"저장 실패");return;}
  $(nameEl).value="";
  await refreshSaved(j.name);
  alert("'"+j.name+"' 으로 저장했습니다.");
}
$("msave").onclick=()=>doSave("mname",pick("tA"));
$("msave2").onclick=()=>doSave("mname2",pick("tB"),job);

// ---------- 코디 패널 (sA = 1단계, sB = 2단계)
// 한 칸을 세 겹으로 고른다:  대분류 → 아이템 → 속성(핏·기장·허리·색·착용)
// 속성은 아이템마다 붙는 축이 달라서, 대분류가 바뀔 때마다 다시 그린다.
const AUTO_="AI가 알아서";
let SY=null;
const AXV={};                    // 속성칸이 다시 그려져도 고른 값을 기억한다
const slotAxHost=(P,k)=>$(P+"-"+k+"__ax");
const slotCat=(P,k)=>$(P+"-"+k+"__cat");
// 저장 키 "하의.핏" → 화면 id "sA-하의__핏"
const styId=(P,k)=>P+"-"+String(k).replace(".","__");

function lookCtl(P,it){
  if(it.type!=="cascade")return ctl(P,it);        // 액세서리·색 조합은 그대로
  const id=P+"-"+it.key;
  return `<div class="wide slot"><label>${esc(it.label)}</label>
    <div class="srow">
      <select class="cat" id="${id}__cat">${
        it.cats.map(c=>`<option>${esc(c.title)}</option>`).join("")}</select>
      <select class="item" id="${id}" data-k="${esc(it.key)}" data-t="select"></select>
    </div>
    <div class="arow" id="${id}__ax"></div></div>`;
}
function catOf(it,val){
  for(const c of it.cats) if(c.options.includes(val)) return c.title;
  return it.cats[0].title;
}
function buildAxes(P,it,cat){
  const host=slotAxHost(P,it.key);
  // 같은 '기장'이라도 팬츠와 스커트는 값이 다르다. 대분류가 들고 있는 축을 그대로 쓴다.
  host.innerHTML=(cat.axes||[]).map(a=>{
    const aid=P+"-"+it.key+"__"+a.key;
    const want=a.options.includes(AXV[aid])?AXV[aid]:a.default;
    return `<span class="ax"><em>${esc(a.label)}</em>
      <select id="${aid}" data-k="${esc(it.key+"."+a.key)}" data-t="select">${
        a.options.map(o=>`<option${o===want?" selected":""}>${esc(o)}</option>`).join("")
      }</select></span>`;
  }).join("");
  host.classList.toggle("hide",!(cat.axes||[]).length);
  host.querySelectorAll("select").forEach(el=>
    el.addEventListener("change",()=>{AXV[el.id]=el.value;syncLook(P);}));
}
function fillSlot(P,it,want){
  const catSel=slotCat(P,it.key), sel=$(P+"-"+it.key);
  const cat=it.cats.find(c=>c.title===catSel.value)||it.cats[0];
  const pick=(want&&cat.options.includes(want))?want:cat.options[0];
  sel.innerHTML=cat.options.map(o=>
    `<option${o===pick?" selected":""}>${esc(o)}</option>`).join("");
  buildAxes(P,it,cat);
}
function eachSlot(fn){ SY.groups.forEach(g=>g.items.forEach(fn)); }

function buildLook(P,host,kindSel){
  host.innerHTML=SY.groups.map(g=>
    `<div class="traits" style="margin-top:12px">
       <div class="wide" style="color:var(--dim);font-size:12px;margin-bottom:-4px">${esc(g.title)}</div>
       ${g.items.map(it=>lookCtl(P,it)).join("")}</div>`).join("");
  kindSel.innerHTML=SY.kinds.map(k=>`<option>${esc(k)}</option>`).join("");
  eachSlot(it=>{
    if(it.type!=="cascade")return;
    const catSel=slotCat(P,it.key);
    catSel.value=catOf(it,it.default);
    fillSlot(P,it,it.default);
    catSel.addEventListener("change",()=>{fillSlot(P,it);syncLook(P);});
    $(P+"-"+it.key).addEventListener("change",()=>syncLook(P));
  });
  host.querySelectorAll("select,input").forEach(el=>{
    if(el.closest(".slot"))return;                // 위에서 따로 달았다
    el.addEventListener("change",()=>syncLook(P));
  });
  kindSel.onchange=()=>syncLook(P);
  syncLook(P);
}
// 제품 종류에 따라 충돌하는 칸을 감추고, 요약 한 줄을 갱신한다
function syncLook(P){
  const kind=$(P==="sA"?"kindA":"kindB").value;
  const hide=(SY.hide[kind]||[]);
  const worn=[];
  eachSlot(it=>{
    const el=$(P+"-"+it.key); if(!el)return;
    const shell=el.closest(".slot")||el.closest("div.wide")||el.closest("div");
    if(shell)shell.classList.toggle("hide",hide.includes(it.key));
    if(hide.includes(it.key)||it.key==="색조합")return;
    if(it.type==="multi"){
      [...el.querySelectorAll("input:checked")].forEach(c=>worn.push(c.value));
      return;
    }
    const v=el.value;
    if(!v||v===AUTO_||(it.none||[]).includes(v))return;
    const c=$(P+"-"+it.key+"__색상");
    worn.push((c&&c.value!=="자동"?c.value+" ":"")+v);
  });
  $(P==="sA"?"sumA":"sumB").textContent = worn.length? "· "+worn.slice(0,4).join(", ")
    + (worn.length>4?" 외 "+(worn.length-4):"") : "";
}
function pickLook(P){
  const kind=$(P==="sA"?"kindA":"kindB").value;
  const hide=(SY.hide[kind]||[]), o={};
  eachSlot(it=>{
    if(hide.includes(it.key))return;
    const el=$(P+"-"+it.key); if(!el)return;
    if(it.type==="multi"){
      const v=[...el.querySelectorAll("input:checked")].map(c=>c.value);
      if(v.length)o[it.key]=v;
      return;
    }
    if(el.value)o[it.key]=el.value;
    const host=slotAxHost(P,it.key);
    if(host)host.querySelectorAll("select").forEach(s=>{o[s.dataset.k]=s.value;});
  });
  return {kind,styling:o};
}
// full=true 면 목록에 없는 항목까지 비운다 (저장된 모델 불러오기).
// 대화로 한두 칸만 고칠 때는 full 없이 부른다 — 안 건드린 칸은 그대로 남아야 한다.
function setLook(P,styling,full){
  if(!SY||!styling)return;
  eachSlot(it=>{
    const el=$(P+"-"+it.key); if(!el)return;
    const v=styling[it.key];
    if(it.type==="multi"){
      if(v===undefined){
        if(full)el.querySelectorAll("input").forEach(c=>c.checked=false);
        return;
      }
      const on=Array.isArray(v)?v:[v];
      el.querySelectorAll("input").forEach(c=>c.checked=on.includes(c.value));
      return;
    }
    if(it.type!=="cascade"){
      if(v!==undefined)el.value=v;
      return;
    }
    if(v!==undefined&&it.options.includes(v)){
      slotCat(P,it.key).value=catOf(it,v);
      fillSlot(P,it,v);
    }
    const host=slotAxHost(P,it.key);                 // 속성값은 있는 것만 반영
    if(host)host.querySelectorAll("select").forEach(s=>{
      const av=styling[s.dataset.k];
      if(av!==undefined&&[...s.options].some(o=>o.value===av)){s.value=av;AXV[s.id]=av;}
    });
  });
  syncLook(P);
}
// 제품명을 적으면 종류를 짐작해서 채운다 (사용자가 손대기 전까지만)
let kindTouched=false;
async function guessKind(){
  if(kindTouched||!SY)return;
  const n=$("name").value.trim(); if(!n)return;
  const r=await fetch("/api/kind?name="+encodeURIComponent(n));
  const k=(await r.json()).kind;
  if(k && $("kindA").value!==k){$("kindA").value=k;syncLook("sA");}
}

let CLOUD=false;
function refreshWhere(){
  fetch("/api/where").then(r=>r.json()).then(w=>{
    CLOUD=!!w.cloud;
    let s;
    if(w.cloud){
      s="서버에서 돌아갑니다. 결과는 <b>[내려받기]</b> 나 <b>[전체 내려받기 (zip)]</b> 로 "+
        "직접 챙겨 주세요 — 서버 안 파일은 오래 남지 않습니다.";
      if(w.limit>0) s+=" 오늘 남은 장수 <b>"+w.left+" / "+w.limit+"</b>.";
      s+=' <a href="#" id="out" style="color:var(--acc)">로그아웃</a>';
    }else{
      s="컷이 나오는 즉시 <b>"+esc(w.outdir)+
        "</b> 안에 제품명 폴더로 자동 저장됩니다. 아래 [내려받기] 는 브라우저 다운로드라 크롬 기본 폴더로 갑니다.";
    }
    $("where").innerHTML=s;
    const o=$("out");
    if(o)o.onclick=async e=>{e.preventDefault();
      await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
      location.reload();};
  });
}
refreshWhere();
fetch("/api/styling").then(r=>r.json()).then(s=>{
  SY=s; buildLook("sA",$("sA"),$("kindA")); buildLook("sB",$("sB"),$("kindB"));
  $("kindA").addEventListener("change",()=>kindTouched=true);
  $("name").addEventListener("blur",guessKind);
});
fetch("/api/traits").then(r=>r.json()).then(g=>{
  G=g; build("tA",$("tA")); build("tB",$("tB")); preview("tA"); preview("tB");
  refreshSaved();
});

// ---------- 사진
$("drop").onclick=()=>$("file").click();
$("file").onchange=e=>load(e.target.files[0]);
["dragenter","dragover"].forEach(t=>$("drop").addEventListener(t,e=>{
  e.preventDefault();$("drop").classList.add("on");}));
["dragleave","drop"].forEach(t=>$("drop").addEventListener(t,e=>{
  e.preventDefault();$("drop").classList.remove("on");}));
$("drop").addEventListener("drop",e=>{if(e.dataTransfer.files[0])load(e.dataTransfer.files[0]);});
function load(f){
  if(!f||!f.type.startsWith("image/"))return;
  const r=new FileReader();
  r.onload=()=>{img=r.result;
    $("drop").innerHTML=`<img src="${img}"><span style="font-size:12px">${esc(f.name)} · 눌러서 변경</span>`;
    if(!$("name").value)$("name").value=f.name.replace(/\.[^.]+$/,"");};
  r.readAsDataURL(f);
}
function show(el,msg){el.textContent=msg;el.classList.toggle("hide",!msg);}

$("drop2").onclick=()=>$("file2").click();
$("file2").onchange=e=>addExtras(e.target.files);
["dragenter","dragover"].forEach(t=>$("drop2").addEventListener(t,e=>{
  e.preventDefault();$("drop2").classList.add("on");}));
["dragleave","drop"].forEach(t=>$("drop2").addEventListener(t,e=>{
  e.preventDefault();$("drop2").classList.remove("on");}));
$("drop2").addEventListener("drop",e=>addExtras(e.dataTransfer.files));
let VIEWS=["뒷면","옆면","디테일","기타"];
fetch("/api/views").then(r=>r.json()).then(v=>{VIEWS=v;drawThumbs();}).catch(()=>{});
function guessView(n){
  const s=(n||"").toLowerCase();
  const map=[["뒷면",["back","rear","뒤","뒷"]],["앞면",["front","앞"]],
    ["옆면",["side","옆","측면"]],["안감",["inside","inner","lining","안감","속"]],
    ["프린트",["print","logo","graphic","프린트","로고"]],
    ["부자재",["button","zip","trim","단추","지퍼","부자재"]],
    ["펼친컷",["flat","lay","펼"]],["착용컷",["worn","wear","model","착용"]],
    ["디테일",["detail","close","macro","texture","디테일","확대"]]];
  for(const [k,keys] of map) if(keys.some(x=>s.includes(x))) return k;
  return "기타";
}
function addExtras(files){
  [...files].slice(0,6-extras.length).forEach(f=>{
    if(!f.type.startsWith("image/"))return;
    const r=new FileReader();
    r.onload=()=>{extras.push({view:guessView(f.name),url:r.result,name:f.name});drawThumbs();};
    r.readAsDataURL(f);
  });
}
function drawThumbs(){
  $("thumbs").innerHTML=extras.map((e,i)=>
    `<figure><img src="${e.url}"><button data-i="${i}">×</button>
     <select data-i="${i}">${VIEWS.map(v=>
       `<option${v===e.view?" selected":""}>${v}</option>`).join("")}</select></figure>`).join("");
  $("thumbs").querySelectorAll("button").forEach(b=>b.onclick=()=>{
    extras.splice(+b.dataset.i,1);drawThumbs();});
  $("thumbs").querySelectorAll("select").forEach(s=>s.onchange=()=>{
    extras[+s.dataset.i].view=s.value;});
}

// ---------- 실행
$("go").onclick=async()=>{
  if(!img){show($("err1"),"옷 사진을 먼저 올려주세요.");return;}
  if(!$("name").value.trim()){show($("err1"),"제품명을 적어주세요.");return;}
  const who=pick("tA");
  if(who===null){show($("err1"),"영어 묘사를 적어주세요.");return;}
  show($("err1"),"");$("go").disabled=true;
  const r=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:$("name").value.trim(),who,image:img,
      graphic:$("gfx").checked,
      extras:extras.map(e=>({view:e.view,url:e.url})),
      ...pickLook("sA")})});
  const j=await r.json();
  if(!j.ok){show($("err1"),j.error);$("go").disabled=false;return;}
  job=j.id;
  $("kindB").value=$("kindA").value;          // 1단계 코디를 2단계로 옮겨 둔다
  setLook("sB",pickLook("sA").styling);
  G.forEach(g=>g.items.forEach(it=>{
    const a=$("tA-"+it.key), b=$("tB-"+it.key); if(!a||!b)return;
    if(it.type==="multi"){
      const on=[...a.querySelectorAll("input:checked")].map(c=>c.value);
      b.querySelectorAll("input").forEach(c=>c.checked=on.includes(c.value));
    }else b.value=a.value;
  }));
  $("cB").value=$("cA").value; $("cBchk").checked=$("cAchk").checked;
  $("cB").classList.toggle("hide",!$("cBchk").checked);
  $("tB").classList.toggle("hide",$("cBchk").checked);
  preview("tB");
  $("step1").classList.add("hide"); $("step2").classList.remove("hide");
  if(window.setQuick)setQuick();          // 2단계용 추천으로 바꿔 준다
  poll();
};

// ---------- 컷·포즈 계획
let PT=null;
const MODEL_CUTS=["wear","side","close"];
fetch("/api/poses").then(r=>r.json()).then(d=>{
  PT=d.pose;
  $("plan").innerHTML=d.cuts.map(p=>{
    const posed=MODEL_CUTS.includes(p.cut);
    let body=`<div class="planrow">
       <input type="checkbox" id="use-${p.cut}" checked>
       <span>${esc(p.label)}</span>`;
    if(posed){
      body+=`<select id="focus-${p.cut}" title="강조 부위">
          ${PT.focus.map(o=>`<option>${esc(o)}</option>`).join("")}</select>
        <select id="base-${p.cut}" title="베이스 포즈">
          ${PT.base.map(o=>`<option>${esc(o)}</option>`).join("")}</select>`;
    }else{
      body+=`<select id="pose-${p.cut}">${p.options.map(o=>`<option>${esc(o)}</option>`).join("")}</select>`;
    }
    body+=`</div>`;
    if(posed){
      body+=`<details class="grp fine"><summary>세부 조정 · ${esc(p.label)}</summary><div>`
        + PT.groups.map(g=>
            `<div class="finegrp"><label>${esc(g.title)}</label><div class="traits">`
            + g.items.map(it=>
                `<div><label>${esc(it.label)}</label>
                   <select data-cut="${p.cut}" data-ax="${esc(it.label)}">
                     ${it.options.map(o=>`<option>${esc(o)}</option>`).join("")}
                   </select></div>`).join("")
            + `</div></div>`).join("")
        + `</div></details>`;
    }
    return body;
  }).join("");
});
function plan(){
  const cuts=[],poses={};
  document.querySelectorAll("#plan .planrow").forEach(row=>{
    const cb=row.querySelector("input[type=checkbox]");
    const cut=cb.id.slice(4);
    if(!cb.checked)return;
    cuts.push(cut);
    if(MODEL_CUTS.includes(cut)){
      const spec={"강조 부위":$("focus-"+cut).value,"베이스 포즈":$("base-"+cut).value};
      document.querySelectorAll(`#plan select[data-cut="${cut}"]`).forEach(sel=>{
        if(sel.value && sel.value!=="지정 안 함") spec[sel.dataset.ax]=sel.value;
      });
      poses[cut]=spec;
    }else{
      const sel=$("pose-"+cut); if(sel) poses[cut]=sel.value;
    }
  });
  return {cuts,poses};
}

$("again").onclick=redo;
async function redo(){
  const who=pick("tB");
  if(who===null){show($("err2"),"영어 묘사를 적어주세요.");return;}
  $("ok").disabled=true;$("again").disabled=true;
  $("heroBox").innerHTML=`<div class="ph" style="aspect-ratio:2/3;border:1px solid var(--line);border-radius:12px">
    <span><span class="spin"></span>만드는 중…</span></div>`;
  show($("err2"),"");
  await fetch("/api/redo",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({id:job,who,...pickLook("sB")})});
  poll();
}
$("ok").onclick=async()=>{
  const {cuts,poses}=plan();
  if(!cuts.length){alert("만들 컷을 하나 이상 골라주세요.");return;}
  $("ok").disabled=true;$("again").disabled=true;
  $("step3").classList.remove("hide");
  await fetch("/api/rest",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({id:job,plan:cuts,poses})});
  poll();
};
$("reset").onclick=()=>location.reload();

// 결과 그리드에서 컷 하나만 다시 뽑기 (위 표의 현재 설정을 그대로 씁니다)
$("grid").addEventListener("click", async e=>{
  const btn=e.target.closest("button.re"); if(!btn)return;
  const cut=btn.dataset.cut;
  btn.disabled=true; btn.textContent="…";
  const {poses}=plan();
  const body={id:job,cut};
  if(poses[cut]!==undefined) body.pose=poses[cut];
  if(cut==="hero"){ body.who=pick("tB"); Object.assign(body,pickLook("sB")); }
  const r=await fetch("/api/redo_cut",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)});
  const j=await r.json();
  if(!j.ok){alert(j.error||"다시 뽑지 못했습니다");btn.disabled=false;btn.textContent="다시";return;}
  poll();
});

function tile(cut,st){
  const url=`/img/${job}/${cut}?v=${st.n}`;
  let inner;
  if(st.state==="done") inner=`<img src="${url}">`;
  else if(st.state==="running") inner=`<div class="ph"><span><span class="spin"></span>만드는 중…</span></div>`;
  else if(st.state==="error") inner=`<div class="ph" style="color:var(--bad)">실패</div>`;
  else if(st.state==="skip") inner=`<div class="ph">선택 안 함</div>`;
  else inner=`<div class="ph">대기</div>`;
  const dl=st.state==="done"
    ?`<a href="${url}" download="${cut}.png" title="브라우저 다운로드 폴더로 받습니다">내려받기</a>`:"";
  const re=(st.state==="done"||st.state==="error"||st.state==="skip")
    ?`<button class="re" data-cut="${cut}" title="위 설정 그대로 이 컷만 다시 만듭니다">다시</button>`:"";
  return `<div class="tile"><div class="shot">${inner}</div>
    <div class="cap"><b>${LABEL[cut]}</b>
    <span class="capr">${dl}${re}</span></div></div>`;
}
async function poll(){
  clearInterval(timer);
  timer=setInterval(async()=>{
    const j=await (await fetch("/api/job?id="+job)).json();
    if(!j.ok){clearInterval(timer);return;}
    const h=j.cuts.hero;
    if(h.state==="done") $("heroBox").innerHTML=`<img src="/img/${job}/hero?v=${h.n}">`;
    else if(h.state==="error"){
      $("heroBox").innerHTML=`<div class="ph" style="aspect-ratio:2/3;color:var(--bad);
        border:1px solid var(--line);border-radius:12px">실패</div>`;
      show($("err2"),h.err);
    }
    if(!$("step3").classList.contains("hide")){
      $("grid").innerHTML=ORDER.map(c=>tile(c,j.cuts[c])).join("");
      const bad=ORDER.find(c=>j.cuts[c].state==="error");
      show($("err2"),bad?j.cuts[bad].err:"");
      const any=ORDER.some(c=>j.cuts[c].state==="done");
      $("zip").classList.toggle("hide",!any);
      if(any)$("zip").href="/zip/"+job;
      if(ORDER.every(c=>["done","error","skip"].includes(j.cuts[c].state))){
        $("saved").innerHTML=CLOUD
          ?"✅ 다 만들었습니다. <b>[전체 내려받기 (zip)]</b> 로 챙겨 가세요."
          :"✅ 6컷 모두 <code>"+esc(j.outdir)+"</code> 에 저장되었습니다.";
        refreshWhere();
        clearInterval(timer);}
    }
    if(!ORDER.some(c=>j.cuts[c].state==="running") && $("step3").classList.contains("hide")){
      $("ok").disabled=false;$("again").disabled=false;clearInterval(timer);
    }
  },2000);
}

// ================================================================ 대화 입력기
// 말한 것을 화면의 선택지로 옮겨 채운다. 그림은 여기서 만들지 않는다.
let CHAT=[];
const step2On=()=>!$("step2").classList.contains("hide");
const P_=()=>step2On()?"tB":"tA";          // 지금 보고 있는 단계의 패널
const S_=()=>step2On()?"sB":"sA";

function chatState(){
  const P=P_(), S=S_(), st={model:{},styling:{},poses:{},cuts:[]};
  if(G) G.forEach(g=>g.items.forEach(it=>{
    const el=$(P+"-"+it.key); if(!el)return;
    if(it.type==="multi"){
      const v=[...el.querySelectorAll("input:checked")].map(c=>c.value);
      if(v.length)st.model[it.key]=v;
    }else if(el.value && el.value!=="지정 안 함") st.model[it.key]=el.value;
  }));
  if(SY){ const L=pickLook(S); st.styling=L.styling; st.kind=L.kind; }
  if(PT && step2On()){
    st.cuts=["wear","side","close","detail","thumb"]
      .filter(c=>$("use-"+c)&&$("use-"+c).checked);
    MODEL_CUTS.forEach(c=>{
      const f=$("focus-"+c), b=$("base-"+c), o={};
      if(f&&f.value&&f.value!=="지정 안 함")o["강조 부위"]=f.value;
      if(b&&b.value&&b.value!=="지정 안 함")o["베이스 포즈"]=b.value;
      if(Object.keys(o).length)st.poses[c]=o;
    });
  }
  st.has_hero=!!(job && $("heroBox").querySelector("img"));
  return st;
}
function mark(el){ if(!el)return; el.classList.remove("justset");
  void el.offsetWidth; el.classList.add("justset"); }

// ---- 바뀐 칸을 이름으로 부르기 위한 표
const shortLab=s=>String(s).replace(/\s*\(.*\)\s*$/,"");   // "액세서리 (여러 개…)" → "액세서리"
function axisLabel(k){
  if(G)for(const g of G)for(const it of g.items)if(it.key===k)return shortLab(it.label||k);
  return k;
}
function styLabel(k){                       // "하의" 또는 "하의.핏"
  const [slot,ax]=String(k).split(".");
  if(SY)for(const g of SY.groups)for(const it of g.items){
    if(it.key!==slot)continue;
    if(!ax)return shortLab(it.label||slot);
    const a=(it.axes||[]).find(x=>x.key===ax);
    return slot+" "+(a?a.label:ax);
  }
  return k;
}
const cutName=c=>(LABEL[c]||c).replace(/^[①-⑥]\s*/,"");
const asText=v=>(Array.isArray(v)?v.join(", "):String(v)).replace(/^기본 — /,"");

// ---- 되돌리기를 위해 바꾸기 직전 값을 떠 둔다
function snap(el){
  if(!el)return null;
  if(el.dataset&&el.dataset.t==="multi")
    return [...el.querySelectorAll("input:checked")].map(c=>c.value);
  if(el.type==="checkbox")return el.checked;
  return el.value;
}
function restore(el,v){
  if(!el)return;
  if(el.dataset&&el.dataset.t==="multi"){
    el.querySelectorAll("input").forEach(c=>{c.checked=v.indexOf(c.value)>=0;}); return;
  }
  if(el.type==="checkbox"){el.checked=v;return;}
  el.value=v;
}

function applyPatch(p){
  const P=P_(), S=S_(), chips=[], undo=[];
  const keep=el=>{ if(el)undo.push(["el",el,snap(el)]); };

  if(G) Object.entries(p.model||{}).forEach(([k,v])=>{
    const el=$(P+"-"+k); if(!el)return;
    keep(el);
    if(el.dataset.t==="multi"){
      const on=Array.isArray(v)?v:[v];
      el.querySelectorAll("input").forEach(c=>{ if(on.includes(c.value))c.checked=true; });
    }else el.value=v;
    mark(el); chips.push({name:axisLabel(k),val:asText(v),el});
  });
  if(G && Object.keys(p.model||{}).length){
    $(P==="tA"?"cAchk":"cBchk").checked=false;
    $(P==="tA"?"cA":"cB").classList.add("hide");
    $(P).classList.remove("hide");
    preview(P);
  }
  if(SY){
    // 코디는 아이템이 바뀌면 속성 칸이 통째로 다시 그려진다. 낱개 칸을 떠 두면
    // 되돌릴 때 이미 사라진 칸을 붙잡게 되므로, 코디는 한 벌을 통째로 떠 둔다.
    const prev=pickLook(S);
    let touched=false;
    if(p.kind){ const k=$(S==="sA"?"kindA":"kindB");
      if(k){k.value=p.kind;mark(k);touched=true;
            chips.push({name:"제품 종류",val:p.kind,id:S==="sA"?"kindA":"kindB"});}
      if(S==="sA")kindTouched=true; }
    const st=p.styling||{};
    if(Object.keys(st).length){
      setLook(S,st);
      Object.keys(st).forEach(k=>{ const el=$(styId(S,k)); if(!el)return;
        mark(el); chips.push({name:styLabel(k),val:asText(st[k]),id:styId(S,k)}); });
      const box=$(S==="sA"?"lookA":"lookB"); if(box)box.open=true;
      touched=true;
    }else if(p.kind) syncLook(S);
    if(touched)undo.push(["look",S,prev]);
  }
  if(step2On()){
    if((p.cuts||[]).length){
      const on=[];
      ["wear","side","close","detail","thumb"].forEach(c=>{
        const el=$("use-"+c); if(!el)return;
        keep(el); el.checked=p.cuts.includes(c); mark(el);
        if(el.checked)on.push(cutName(c));
      });
      chips.push({name:"만들 컷",val:on.join(", ")||"없음",el:$("use-wear")});
    }
    Object.entries(p.poses||{}).forEach(([cut,sel])=>{
      Object.entries(sel).forEach(([ax,v])=>{
        let el=null;
        if(ax==="강조 부위")el=$("focus-"+cut);
        else if(ax==="베이스 포즈")el=$("base-"+cut);
        else el=document.querySelector("#plan select[data-cut='"+cut+"'][data-ax='"+ax+"']");
        if(el){keep(el);el.value=v;mark(el);
               chips.push({name:cutName(cut)+" "+ax,val:asText(v),el});}
      });
    });
  }
  return {chips,undo};
}

// ---- 칩: 눌러서 확인하고, 눌러서 되돌리고, 눌러서 다음 말을 보낸다
function chip(cls,html,fn){
  const b=document.createElement("button");
  b.type="button"; b.className="kchip "+cls; b.innerHTML=html; b.onclick=fn;
  return b;
}
function reveal(c){                        // 그 칸이 어디 있는지 눈으로 보여준다
  const el=c.el||$(c.id);                  // 다시 그려졌을 수 있어 누를 때 찾는다
  if(!el)return;
  let d=el.closest("details");
  while(d){ d.open=true; d=d.parentElement&&d.parentElement.closest("details"); }
  el.scrollIntoView({behavior:"smooth",block:"center"});
  el.classList.remove("ping"); void el.offsetWidth; el.classList.add("ping");
}
function undoPatch(undo,row){
  undo.slice().reverse().forEach(u=>{
    if(u[0]==="look"){                     // 코디 한 벌 통째로
      const S=u[1], prev=u[2];
      const k=$(S==="sA"?"kindA":"kindB"); if(k&&prev.kind)k.value=prev.kind;
      setLook(S,prev.styling,true);
      return;
    }
    restore(u[1],u[2]);
  });
  if(SY)syncLook(S_());
  if(G)preview(P_());
  row.remove(); fitChat();
  chatSay("ai","되돌렸습니다.");
}
function showChips(bubble,chips,undo){
  if(!chips.length)return;
  const row=document.createElement("div"); row.className="krow";
  chips.slice(0,14).forEach(c=>row.appendChild(
    chip("set","<i>"+esc(c.name)+"</i><b>"+esc(c.val)+"</b>",()=>reveal(c))));
  if(chips.length>14)row.appendChild(
    chip("","<i>그 밖</i><b>"+(chips.length-14)+"개</b>",()=>{}));
  row.appendChild(chip("undo","↩ 되돌리기",()=>undoPatch(undo,row)));
  bubble.appendChild(row);
}

// ---- 다음에 눌러볼 말. 안 물어봐도 고를 거리를 보여준다.
const START1=["여성 20대 초반, 청순하게","남성 20대 후반, 시크하게",
              "분위기까지 알아서 채워줘","코디는 알아서 잡아줘"];
const NEXT1 =["좀 더 어리게","코디는 알아서 잡아줘","머리 더 길게","대표컷 뽑아줘"];
const START2=["포즈 컷마다 다르게","컷은 착용컷 두 장만","나머지 컷 만들어줘"];
function fallbackQuick(){
  if(step2On())return START2;
  const st=chatState().model||{};
  return Object.keys(st).length>1 ? NEXT1 : START1;   // 이미 잡은 게 있으면 다음 걸음으로
}
function setQuick(list){
  const q=$("quick"); q.innerHTML="";
  const use=(list&&list.length)?list:fallbackQuick();
  const lab=document.createElement("span");
  lab.className="qlab"; lab.textContent="눌러서 →";
  q.appendChild(lab);
  use.slice(0,5).forEach(t=>q.appendChild(chip("",esc(t),()=>{
    $("chatin").value=t; sendChat();
  })));
  fitChat();
}
// 대화창 높이가 바뀌면 본문 아래 여백도 같이 바뀐다
function fitChat(){
  const bar=$("chatbar");
  document.body.style.paddingBottom =
    bar.classList.contains("hide") ? "" : (bar.offsetHeight+26)+"px";
}
function runFromChat(run){
  if(run==="hero") return (step2On()?$("again"):$("go")).click(), "대표컷을 만들겠습니다.";
  if(run==="rest"){ if(step2On()){ $("ok").click(); return "나머지 컷을 만들겠습니다."; } return ""; }
  if(run.indexOf("cut:")===0){
    const b=document.querySelector("#grid button.re[data-cut='"+run.slice(4)+"']");
    if(b){ b.click(); return "그 컷만 다시 뽑겠습니다."; }
  }
  return "";
}
// 사진 생성은 장당 요금이 든다. 잘못 알아들었을 수 있으니 한 번 확인받는다.
const RUNLABEL={hero:"대표컷을 만들까요?",rest:"나머지 컷을 만들까요?"};
function askRun(run){
  const label=RUNLABEL[run]||"그 컷만 다시 뽑을까요?";
  const d=document.createElement("div");
  d.className="m ai ask";
  d.innerHTML='<span>'+esc(label)+' <button class="yes mini">네, 만들게요</button>'
            + '<button class="no ghost mini">아니오</button></span>';
  $("chatlog").appendChild(d);
  $("chatlog").classList.remove("hide");
  $("chatlog").scrollTop=$("chatlog").scrollHeight;
  fitChat();
  const done=t=>{ d.querySelectorAll("button").forEach(b=>b.remove());
                  d.querySelector("span").appendChild(document.createTextNode(" — "+t)); };
  d.querySelector(".yes").onclick=()=>{ const m=runFromChat(run); done(m||"실행했습니다."); };
  d.querySelector(".no").onclick=()=>done("그만뒀습니다.");
}
function chatSay(who,text,bad){
  const d=document.createElement("div");
  d.className="m "+(who==="me"?"me":"ai")+(bad?" bad":"");
  d.innerHTML="<span>"+esc(text)+"</span>";
  $("chatlog").appendChild(d); $("chatlog").classList.remove("hide");
  $("chatlog").scrollTop=$("chatlog").scrollHeight;
  fitChat();
  return d;
}
let chatBusy=false;
async function sendChat(){
  if(chatBusy)return;                                   // 연달아 눌러도 한 번만
  const msg=$("chatin").value.trim(); if(!msg)return;
  chatBusy=true;
  $("chatin").value=""; chatSay("me",msg);
  $("chatgo").disabled=true; $("chatgo").textContent="…";
  try{
    const r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({msg,history:CHAT.slice(),state:chatState()})});
    const j=await r.json();
    CHAT.push({role:"user",content:msg});
    if(!j.ok){ chatSay("ai",j.error||"알아듣지 못했습니다.",true); return; }
    const {chips,undo}=applyPatch(j);
    const wants=(j.run&&j.run!=="none")?j.run:"";
    let say=j.say;
    // 포즈·컷은 2단계에만 있는 칸이라, 1단계에서는 받아 둘 곳이 없다
    const later=!step2On()&&(Object.keys(j.poses||{}).length||(j.cuts||[]).length);
    if(later)say+=" (포즈와 컷은 대표컷을 만든 뒤 2단계에서 정해집니다)";
    else if(!chips.length&&!wants)say+=" (바뀐 항목은 없습니다)";
    const bubble=chatSay("ai",say);
    showChips(bubble,chips,undo);    // 무엇이 어떻게 바뀌었는지 눈으로
    setQuick(j.tips);                // 다음에 눌러볼 말
    $("chatlog").scrollTop=$("chatlog").scrollHeight;
    if(wants)askRun(wants);          // 돈이 드는 일이라 바로 실행하지 않는다
    CHAT.push({role:"assistant",content:j.say});
    if(CHAT.length>24)CHAT=CHAT.slice(-24);
  }catch(e){ chatSay("ai",String(e),true); }
  finally{ chatBusy=false; $("chatgo").disabled=false;
           $("chatgo").textContent="보내기"; $("chatin").focus(); }
}
$("chatgo").onclick=sendChat;
// 한글·일본어·중국어 입력기는 마지막 글자를 "조합 중" 상태로 들고 있다가
// Enter 로 확정한다. 그 Enter 까지 전송으로 처리하면 확정된 글자가 빈 칸에 남아
// 한 번 더 보내진다 ("가방 없애줘" → "줘"). 조합 중일 때는 보내지 않는다.
let composing=false;
$("chatin").addEventListener("compositionstart",()=>{composing=true;});
$("chatin").addEventListener("compositionend",()=>{composing=false;});
$("chatin").addEventListener("keydown",e=>{
  if(e.key!=="Enter")return;
  if(e.isComposing||composing||e.keyCode===229)return;   // 조합 확정용 Enter
  e.preventDefault();
  sendChat();
});
$("chattoggle").onclick=()=>{
  const l=$("chatlog");
  if(!l.children.length){ $("chint").textContent="아직 주고받은 말이 없습니다."; return; }
  l.classList.toggle("hide");
};
// 채팅 열기·닫기. 닫아도 대화 내역은 남는다.
function chatShow(on){
  $("chatbar").classList.toggle("hide",!on);
  $("chatopen").classList.toggle("hide",on);
  document.body.classList.toggle("chaton",on);
  fitChat();
  if(on)$("chatin").focus();
}
$("chatclose").onclick=()=>chatShow(false);
$("chatopen").onclick=()=>chatShow(true);
document.addEventListener("keydown",e=>{                 // Esc 로도 닫힌다
  if(e.key==="Escape" && !$("chatbar").classList.contains("hide"))chatShow(false);
});
setQuick();
chatShow(true);
addEventListener("resize",fitChat);

</script></body></html>
"""


# ----------------------------------------------------------------- 서버
class H(BaseHTTPRequestHandler):
    server_version = "GoodsWeb/1.0"
    protocol_version = "HTTP/1.1"

    _cookie = ""

    def js(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(),
                  "application/json; charset=utf-8")

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60 * 1024 * 1024:
            raise ValueError("보낸 내용이 너무 큽니다")
        return json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")

    # ---------------------------------------------------------- 로그인
    def who(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and token_ok(v):
                return True
        return False

    def authed(self):
        return (not need_auth()) or self.who()

    def client_ip(self):
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or self.client_address[0]

    def set_cookie(self, val, secs):
        bits = ["%s=%s" % (COOKIE, val), "Path=/", "HttpOnly", "SameSite=Lax",
                "Max-Age=%d" % secs]
        if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https":
            bits.append("Secure")
        self._cookie = "; ".join(bits)

    def send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):       # 글꼴처럼 안 바뀌는 것은 캐시한다
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if getattr(self, "_cookie", ""):
            self.send_header("Set-Cookie", self._cookie)
            self._cookie = ""
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if not self.authed():
            if path.startswith("/api/") or path.startswith("/img/") \
               or path.startswith("/mthumb/") or path.startswith("/zip/"):
                return self.js({"ok": False, "error": "로그인이 필요합니다.",
                                "login": True}, 401)
            return self.send(200, LOGIN.encode(), "text/html; charset=utf-8")
        if path == "/":
            return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
        if path == "/pretendard.woff2":
            fp = os.path.join(HERE, "pretendard.woff2")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return self.send(200, f.read(), "font/woff2",
                                     {"Cache-Control": "public, max-age=31536000, immutable"})
            return self.send(404, b"not found", "text/plain")

        if path == "/api/poses":
            return self.js({"cuts": gs.poses_json(), "pose": gs.pose_traits_json()})

        if path == "/api/models":
            d = gs.load_models()
            return self.js([{"name": k, "desc": v.get("묘사", ""),
                             "saved": v.get("저장", ""), "thumb": bool(v.get("썸네일"))}
                            for k, v in d.items()])

        if path.startswith("/api/model_get"):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            name = (q.get("name") or [""])[0]
            return self.js({"who": gs.get_model(name), "styling": gs.get_look(name)})

        if path == "/api/where":
            d = {"outdir": OUTDIR, "cloud": need_auth()}
            d.update(quota_state())
            return self.js(d)

        if path == "/api/views":
            return self.js(gs.VIEW_ORDER)

        if path == "/api/styling":
            return self.js(gs.styling_traits_json())

        if path.startswith("/api/kind"):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            return self.js({"kind": gs.guess_kind((q.get("name") or [""])[0])})

        if path == "/api/traits":
            return self.js(gs.traits_json())
        if path == "/api/job":
            q = dict(p.split("=", 1) for p in self.path.split("?")[1].split("&")) \
                if "?" in self.path else {}
            job = JOBS.get(q.get("id", ""))
            if not job:
                return self.js({"ok": False, "error": "작업을 찾을 수 없습니다."}, 404)
            return self.js({"ok": True, "cuts": job["cuts"], "outdir": job["outdir"]})
        m = re.match(r"^/mthumb/(.+)$", path)
        if m:
            fp = os.path.join(gs.STORE_THUMBS, urllib.parse.unquote(m.group(1)) + ".png")
            if os.path.isfile(os.path.abspath(fp)) and \
               os.path.abspath(fp).startswith(os.path.abspath(gs.STORE_THUMBS)):
                with open(fp, "rb") as f:
                    return self.send(200, f.read(), "image/png")
            return self.send(404, b"not found", "text/plain")

        m = re.match(r"^/zip/([0-9a-f]+)$", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job or not job.get("bytes"):
                return self.send(404, b"not found", "text/plain")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for cut in gs.CUTS:
                    blob = job["bytes"].get(cut)
                    if blob:
                        z.writestr("%s_%s%s" % (gs.LABEL[cut].replace(" ", ""), cut,
                                                gs.ext_for(blob)), blob)
                raw = (job.get("garment") or "").split(",", 1)
                if len(raw) == 2:
                    src = base64.b64decode(raw[1])
                    z.writestr("_원본" + gs.ext_for(src), src)
                for i, e in enumerate(job.get("extras") or [], 1):
                    raw = (e["url"] or "").split(",", 1)
                    if len(raw) == 2:
                        src = base64.b64decode(raw[1])
                        z.writestr("_원본_%d_%s%s" % (i, e["view"], gs.ext_for(src)), src)
            data = buf.getvalue()
            fn = urllib.parse.quote(gs.safe_dir(job["name"]) + ".zip")
            return self.send(200, data, "application/zip",
                             {"Content-Disposition":
                              "attachment; filename*=UTF-8''" + fn})

        m = re.match(r"^/img/([0-9a-f]+)/([a-z]+)$", path)
        if m:
            job = JOBS.get(m.group(1))
            blob = (job or {}).get("bytes", {}).get(m.group(2))
            if not blob:
                return self.send(404, b"not found", "text/plain")
            return self.send(200, blob, gs.sniff_mime(blob))
        return self.send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            b = self.body_json()
        except Exception as e:
            return self.js({"ok": False, "error": "요청을 읽지 못했습니다: %s" % e}, 400)

        if path == "/api/login":
            ip = self.client_ip()
            if locked_out(ip):
                return self.js({"ok": False,
                                "error": "여러 번 틀렸습니다. 5분 뒤에 다시 해주세요."}, 429)
            ok = need_auth() and hmac.compare_digest(str(b.get("pw") or ""), APP_PASSWORD)
            note_login(ip, ok)
            if not ok:
                time.sleep(0.7)
                return self.js({"ok": False, "error": "비밀번호가 맞지 않습니다."}, 401)
            self.set_cookie(make_token(), SESSION_HOURS * 3600)
            return self.js({"ok": True})

        if path == "/api/logout":
            self.set_cookie("", 0)
            return self.js({"ok": True})

        if not self.authed():
            return self.js({"ok": False, "error": "로그인이 필요합니다.", "login": True}, 401)

        if path == "/api/start":
            if not gs.OR_KEY:
                return self.js({"ok": False,
                                "error": "OPENROUTER_API_KEY 가 설정되지 않았습니다. "
                                         "터미널에서 export 한 뒤 다시 실행하세요."})
            img = b.get("image") or ""
            if not img.startswith("data:image/"):
                return self.js({"ok": False, "error": "이미지를 읽지 못했습니다."})
            jid = new_job(b.get("name", "").strip() or "product",
                          b.get("who") or "", img, b.get("extras"), b.get("graphic"),
                          b.get("kind") or "", b.get("styling") or {})
            spawn(run_hero, jid)
            return self.js({"ok": True, "id": jid})

        if path == "/api/model_save":
            try:
                thumb = None
                jid = b.get("job")
                if jid and jid in JOBS:
                    thumb = JOBS[jid]["bytes"].get("hero")
                name = gs.save_model(b.get("name"), b.get("who"), thumb,
                                     b.get("styling") or {})
                return self.js({"ok": True, "name": name})
            except Exception as e:
                return self.js({"ok": False, "error": str(e)[:200]})

        if path == "/api/model_delete":
            return self.js({"ok": gs.delete_model(str(b.get("name") or ""))})

        if path == "/api/chat":
            if ca is None:
                return self.js({"ok": False, "error": "chat_agent.py 를 찾지 못했습니다."})
            try:
                out = ca.reply(b.get("history") or [], b.get("msg"),
                               b.get("state") or {}, gs.chat)
                return self.js({"ok": True, **out})
            except Exception as e:
                return self.js({"ok": False, "error": str(e)[:300]})

        if path == "/api/preview":
            try:
                return self.js({"desc": gs.model_desc(b.get("who"))})
            except Exception as e:
                return self.js({"desc": "묘사를 만들지 못했습니다: %s" % e})

        if path == "/api/redo":
            jid = b.get("id", "")
            if jid not in JOBS:
                return self.js({"ok": False, "error": "작업을 찾을 수 없습니다."}, 404)
            apply_look(JOBS[jid], b)
            spawn(run_hero, jid, b.get("who"))
            return self.js({"ok": True})

        if path == "/api/redo_cut":
            jid, cut = b.get("id", ""), b.get("cut", "")
            if jid not in JOBS or cut not in gs.CUTS:
                return self.js({"ok": False, "error": "다시 뽑을 컷을 찾을 수 없습니다."}, 404)
            job = JOBS[jid]
            apply_look(job, b)
            pose = b.get("pose")
            if isinstance(pose, dict) or (isinstance(pose, str) and pose):
                job.setdefault("poses", {})[cut] = pose
            if b.get("who") is not None:
                job["who"] = b.get("who")
            if cut == "hero":
                spawn(run_hero, jid)
            else:
                if not job["bytes"].get("hero"):
                    return self.js({"ok": False, "error": "대표컷이 먼저 있어야 합니다."})
                job["cuts"][cut] = {"state": "idle", "err": "",
                                    "n": job["cuts"][cut].get("n", 0)}
                spawn(run_one, jid, cut)
            return self.js({"ok": True})

        if path == "/api/rest":
            jid = b.get("id", "")
            if jid not in JOBS:
                return self.js({"ok": False, "error": "작업을 찾을 수 없습니다."}, 404)
            job = JOBS[jid]
            plan = [c for c in (b.get("plan") or REST) if c in REST]
            job["plan"] = plan or list(REST)
            poses = b.get("poses") or {}
            clean_poses = {}
            for k, v in poses.items():
                if isinstance(v, dict):
                    clean_poses[k] = v
                elif k in gs.POSES and v in gs.POSES[k]:
                    clean_poses[k] = v
            job["poses"] = clean_poses
            for c in REST:                     # 이번에 안 뽑는 컷은 대기 상태로 되돌린다
                if c not in job["plan"] and job["cuts"][c]["state"] != "done":
                    job["cuts"][c] = {"state": "skip", "err": "", "n": 0}
            spawn(run_rest, jid)
            return self.js({"ok": True, "plan": job["plan"]})

        return self.js({"ok": False, "error": "알 수 없는 주소"}, 404)

    def log_message(self, *a):
        pass


def main():
    global OUTDIR, MODEL, SIZE
    ap = argparse.ArgumentParser(description="상세페이지 이미지 만들기 (웹 화면)")
    # 서버(Render 등)에 올리면 PORT 환경변수가 들어온다 → 그때는 밖에서 접속받는다
    env_port = os.environ.get("PORT")
    ap.add_argument("--port", type=int, default=int(env_port) if env_port else 8765)
    ap.add_argument("--host", default=os.environ.get("HOST") or
                    ("0.0.0.0" if env_port else "127.0.0.1"),
                    help="0.0.0.0 이면 서버 모드 (밖에서 접속 가능)")
    ap.add_argument("--outdir", default=os.environ.get("OUTDIR") or OUTDIR,
                    help="결과 저장 폴더")
    ap.add_argument("--model", default=os.environ.get("IMAGE_MODEL") or MODEL)
    ap.add_argument("--size", default=os.environ.get("IMAGE_SIZE") or SIZE,
                    choices=["512", "1K", "2K", "4K"])
    ap.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = ap.parse_args()
    OUTDIR = os.path.abspath(os.path.expanduser(args.outdir))
    MODEL, SIZE = args.model, args.size
    server_mode = args.host not in ("127.0.0.1", "localhost")

    if server_mode and not need_auth():
        sys.exit("밖에서 접속받는 모드인데 APP_PASSWORD 가 없습니다.\n"
                 "누구나 들어와 키를 쓰게 되므로 막았습니다. "
                 "APP_PASSWORD 를 정해서 환경변수로 넣고 다시 실행하세요.")

    url = "http://127.0.0.1:%d" % args.port
    print("─" * 56)
    print(" 상세페이지 이미지 만들기")
    print(" 주소   : %s" % (url if not server_mode else "0.0.0.0:%d (서버 모드)" % args.port))
    print(" 저장   : %s" % OUTDIR)
    print(" 모델   : %s (%s)" % (MODEL, SIZE))
    print(" 키     : %s" % ("설정됨" if gs.OR_KEY else "❗ OPENROUTER_API_KEY 없음"))
    print(" 로그인 : %s" % ("비밀번호 필요" if need_auth() else "없음 (내 컴퓨터 전용)"))
    print(" 한도   : %s" % ("하루 %d장" % DAILY_LIMIT if DAILY_LIMIT > 0 else "제한 없음"))
    print(" 끄기   : 이 창에서 Control + C")
    print("─" * 56)
    if not args.no_open and not server_mode:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv = ThreadingHTTPServer((args.host, args.port), H)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
