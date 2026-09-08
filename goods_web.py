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


def new_job(name, who, garment_dataurl, extras=None, graphic=False):
    jid = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[jid] = {
            "id": jid, "name": name, "who": who,
            "garment": garment_dataurl,
            "extras": norm_extras(extras), "graphic": bool(graphic),
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
                                 pose=(job.get("poses") or {}).get(cut))
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


def spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ----------------------------------------------------------------- 화면
LOGIN = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>상세페이지 이미지 만들기 · 로그인</title>
<style>
:root{--bg:#faf9f7;--fg:#1c1917;--dim:#78716c;--card:#fff;--line:#e7e5e4;
      --acc:#c2410c;--bad:#b91c1c;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#e7e5e4;--dim:#a8a29e;
      --card:#1c1917;--line:#292524;--acc:#ea580c;--bad:#f87171}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:var(--bg);color:var(--fg);padding:24px;
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard",sans-serif}
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
:root{--bg:#faf9f7;--fg:#1c1917;--dim:#78716c;--card:#fff;--line:#e7e5e4;
      --acc:#c2410c;--bad:#b91c1c;--soft:#f5f5f4;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#e7e5e4;--dim:#a8a29e;
      --card:#1c1917;--line:#292524;--acc:#ea580c;--bad:#f87171;--soft:#1c1917}}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--fg);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
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
button{padding:11px 20px;border:0;border-radius:10px;background:var(--acc);color:#fff;
 font:600 14px/1 inherit;cursor:pointer}
button.ghost{background:transparent;color:var(--fg);border:1px solid var(--line)}
button.mini{padding:6px 12px;font-size:12.5px}
button:disabled{opacity:.45;cursor:default}
.btns{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
.hero{display:grid;grid-template-columns:290px 1fr;gap:22px;align-items:start}
@media(max-width:820px){.hero{grid-template-columns:1fr}}
.hero img{width:100%;border-radius:12px;border:1px solid var(--line);display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:14px;margin-top:6px}
.tile{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card)}
.tile .ph{aspect-ratio:2/3;display:flex;align-items:center;justify-content:center;
 color:var(--dim);font-size:12.5px;background:var(--soft);text-align:center;padding:10px}
.tile img{width:100%;display:block}
.tile .cap{padding:8px 10px;font-size:12.5px;color:var(--dim);display:flex;justify-content:space-between;gap:6px}
.tile a{color:var(--acc);text-decoration:none}
.tile .capr{display:flex;gap:8px;align-items:center}
.tile .re{padding:3px 9px;font-size:11.5px;background:transparent;color:var(--acc);
 border:1px solid var(--line);border-radius:999px}
.err{color:var(--bad);font-size:13px;margin-top:10px;white-space:pre-wrap;word-break:break-word}
.note{color:var(--dim);font-size:12.5px;margin-top:12px}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--line);
 border-top-color:var(--acc);border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
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
  if(it.type==="multi")
    return `<div class="wide"><label>${esc(it.label)}</label>
      <div class="chips" id="${id}" data-k="${it.key}" data-t="multi">
        ${it.options.map(o=>`<label class="chip"><input type="checkbox" value="${esc(o)}">${esc(o)}</label>`).join("")}
      </div></div>`;
  return `<div><label>${esc(it.label)}</label>
    <select id="${id}" data-k="${it.key}" data-t="select">
      ${it.options.map(o=>`<option${o===it.default?" selected":""}>${esc(o)}</option>`).join("")}
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
    const who=(await r.json()).who;
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
    body:JSON.stringify({name,who,job:jobId||null})});
  const j=await r.json();
  if(!j.ok){alert(j.error||"저장 실패");return;}
  $(nameEl).value="";
  await refreshSaved(j.name);
  alert("'"+j.name+"' 으로 저장했습니다.");
}
$("msave").onclick=()=>doSave("mname",pick("tA"));
$("msave2").onclick=()=>doSave("mname2",pick("tB"),job);

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
      extras:extras.map(e=>({view:e.view,url:e.url}))})});
  const j=await r.json();
  if(!j.ok){show($("err1"),j.error);$("go").disabled=false;return;}
  job=j.id;
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
    body:JSON.stringify({id:job,who})});
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
  if(cut==="hero") body.who=pick("tB");
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
  return `<div class="tile">${inner}<div class="cap"><span>${LABEL[cut]}</span>
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
            return self.js({"who": gs.get_model(name)})

        if path == "/api/where":
            d = {"outdir": OUTDIR, "cloud": need_auth()}
            d.update(quota_state())
            return self.js(d)

        if path == "/api/views":
            return self.js(gs.VIEW_ORDER)

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
                          b.get("who") or "", img, b.get("extras"), b.get("graphic"))
            spawn(run_hero, jid)
            return self.js({"ok": True, "id": jid})

        if path == "/api/model_save":
            try:
                thumb = None
                jid = b.get("job")
                if jid and jid in JOBS:
                    thumb = JOBS[jid]["bytes"].get("hero")
                name = gs.save_model(b.get("name"), b.get("who"), thumb)
                return self.js({"ok": True, "name": name})
            except Exception as e:
                return self.js({"ok": False, "error": str(e)[:200]})

        if path == "/api/model_delete":
            return self.js({"ok": gs.delete_model(str(b.get("name") or ""))})

        if path == "/api/preview":
            try:
                return self.js({"desc": gs.model_desc(b.get("who"))})
            except Exception as e:
                return self.js({"desc": "묘사를 만들지 못했습니다: %s" % e})

        if path == "/api/redo":
            jid = b.get("id", "")
            if jid not in JOBS:
                return self.js({"ok": False, "error": "작업을 찾을 수 없습니다."}, 404)
            spawn(run_hero, jid, b.get("who"))
            return self.js({"ok": True})

        if path == "/api/redo_cut":
            jid, cut = b.get("id", ""), b.get("cut", "")
            if jid not in JOBS or cut not in gs.CUTS:
                return self.js({"ok": False, "error": "다시 뽑을 컷을 찾을 수 없습니다."}, 404)
            job = JOBS[jid]
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
