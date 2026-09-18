#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대화 입력기
===========
화면을 없애지 않는다. 말로 한 것을 **화면의 선택지로 번역해서 채워 넣는다.**

    "20대 초반 여성, 청순하게. 하의는 검정 슬랙스"
        → 성별 표현=여성 / 보이는 연령=20대 초반 / 전체 인상=청순한 / 하의=검정 슬랙스
        → 드롭다운이 눈앞에서 바뀌고, 사장님이 보고 고칠 수 있다

이렇게 하는 이유
----------------
* 무엇을 알아들었는지 **뽑기 전에** 눈으로 확인할 수 있다.
* compose() 가 만드는 정교한 영어 프롬프트를 그대로 쓴다.
  자유 문장을 이미지 모델에 바로 던지면 공들인 잠금 문구가 힘을 잃는다.
* 선택지는 화면에 계속 보인다. 채팅만 있으면 "뭘 물어봐야 하는지"를 모른다.

대화는 이어진다
---------------
직전까지의 설정을 함께 넘기므로 "좀 더 어리게", "머리 더 길게" 같은
상대적인 수정이 된다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_traits as mt                                     # noqa: E402
import pose_traits as pt                                      # noqa: E402
import styling_traits as sy                                   # noqa: E402

NONE = "지정 안 함"
CUTS = {"hero": "대표컷", "wear": "정면 착용", "side": "측면 착용",
        "close": "상반신", "detail": "원단 디테일", "thumb": "썸네일"}
POSE_CUTS = ["wear", "side", "close", "detail", "thumb"]
MAX_TURNS = 12          # 이보다 오래된 대화는 잘라낸다


# ------------------------------------------------------------- 선택지 목록
def _axis_lines(items, key="key"):
    """축 하나에 한 줄. 소분류가 있으면 [갈래] 로 묶어서 적는다 —
    AI 가 '어느 갈래에서 고르는 중인지' 알면 엉뚱한 값을 덜 고른다."""
    out = []
    for it in items:
        k = it.get(key) or it.get("label")
        opts = [o for o in (it.get("options") or []) if o != NONE]
        if not opts:
            continue
        gs = [g for g in (it.get("optgroups") or []) if g.get("title")]
        if gs:
            body = " ".join("[%s] %s" % (g["title"], " / ".join(g["options"])) for g in gs)
            inside = {o for g in gs for o in g["options"]}
            rest = [o for o in opts if o not in inside]       # 갈래에 안 들어간 값 (AI가 알아서 등)
            if rest:
                body += " / " + " / ".join(rest)
        else:
            body = " / ".join(opts)
        out.append("%s: %s" % (k, body))
    return out


def catalog():
    """AI 에게 넘길 전체 선택지 목록. 여기 없는 값은 쓰지 못하게 한다."""
    L = ["### 모델 (키는 영문 key 를 그대로 쓸 것)"]
    for g in mt.traits_json():
        L.append("[%s]" % g["title"])
        L += _axis_lines(g["items"], "key")

    L.append("")
    L.append("### 코디 (키는 한글 그대로)")
    s = sy.traits_json()
    L.append("제품종류: " + " / ".join(s["kinds"]))
    for g in s["groups"]:
        for it in g["items"]:
            if it.get("type") == "cascade":
                L.append("%s: %s" % (it["key"], " ".join(
                    "[%s] %s" % (c["title"], " / ".join(c["options"])) for c in it["cats"])))
                # 같은 축이라도 대분류마다 값이 다를 수 있다 (하의.기장: 팬츠 vs 스커트)
                seen = []
                for c in it["cats"]:
                    for a in c["axes"]:
                        sig = (a["key"], tuple(a["options"]))
                        hit = next((s for s in seen if s[0] == sig), None)
                        if hit:
                            hit[1].append(c["title"])
                        else:
                            seen.append((sig, [c["title"]]))
                for (akey, opts), cats in seen:
                    L.append("%s.%s: %s   (%s 일 때)" % (
                        it["key"], akey, " / ".join(opts), "·".join(cats)))
            else:
                L += _axis_lines([it], "key")

    L.append("")
    L.append("### 포즈 (키는 한글 그대로, 컷마다 따로 지정)")
    p = pt.traits_json()
    L.append("강조 부위: " + " / ".join(p["focus"]))
    L.append("베이스 포즈: " + " / ".join(p["base"]))
    for g in p["groups"]:
        L += _axis_lines(g["items"], "label")

    L.append("")
    L.append("### 컷 이름")
    L.append(" / ".join("%s=%s" % (v, k) for k, v in CUTS.items()))
    return "\n".join(L)


SYSTEM = """너는 옷 상세페이지용 모델컷을 만드는 도구의 입력 도우미다.
사용자가 한국어로 말하면, 그 말을 화면의 선택 항목으로 옮겨 적는 것이 네 일이다.

절대 규칙
- 아래 목록에 **그대로 적힌 값만** 쓴다. 비슷한 말을 지어내지 않는다.
- 딱 맞는 값이 없으면 그 항목은 건드리지 말고, 말로 "그건 선택지에 없어요"라고 알린다.
  가까운 값이 있으면 그것으로 잡고 무엇으로 바꿨는지 반드시 말한다.
- **이번에 바뀌는 항목만** 넣는다. 그대로 두는 항목은 넣지 않는다.
- "좀 더 어리게", "머리 더 길게" 처럼 상대적으로 말하면 지금 설정을 기준으로 한 칸 옮긴다.
- 사진 생성은 돈이 든다. 사용자가 "뽑아줘 / 만들어줘 / 시작해" 처럼 **분명히 시킬 때만** 실행한다.
  그 외에는 설정만 바꾸고 실행하지 않는다.
- 사용자가 "뭐 고를 수 있어?" 처럼 물으면 실행하지 말고 대표적인 선택지를 말로 알려준다.
- 답변은 한국어로 두 문장 이내. 무엇을 바꿨는지 짧게. 인사말·사족은 붙이지 않는다.

한 번에 많이 채워주기
- 이 도구의 목적은 **사장님이 일일이 고르지 않게 하는 것**이다.
- "알아서", "추천해줘", "다 채워줘", "아무거나" 라고 하면
  아직 비어 있는 항목들을 한 번에 그럴듯하게 채운다. 하나씩 되묻지 않는다.
- 한 마디만 던져도(예: "청순한 20대 여성") 그 분위기에 맞게 머리·피부·표정·코디까지
  같이 잡아 준다. 사용자가 콕 집어 말한 항목은 절대 건드리지 않는다.

반드시 아래 JSON 형식으로만 답한다.
{
  "말": "사용자에게 보여줄 짧은 한국어 답변",
  "모델": {"영문key": "값"},
  "코디": {"한글키": "값"},
  "제품종류": "상의",
  "포즈": {"wear": {"강조 부위": "소매", "베이스 포즈": "워킹"}},
  "컷": ["wear", "side"],
  "실행": "none",
  "추천": ["다음에 눌러볼 만한 짧은 말", "또 하나"]
}
- 바꿀 게 없는 칸은 빈 객체 {} 또는 빈 배열 [] 로 둔다.
- "제품종류"는 바꿀 때만 넣는다.
- "컷"은 만들 컷을 사용자가 정했을 때만 넣는다.
- "실행"은 "none" / "hero"(대표컷) / "rest"(나머지 컷) / "cut:wear" 처럼 컷 하나 중 하나.
- 액세서리·얼굴 특징처럼 여러 개 고르는 항목은 값을 배열로 넣는다.
- 코디는 **아이템 + 속성** 두 겹이다. 속성 키는 "하의.핏" 처럼 점으로 잇는다.
  예) "밑단 넓은 청바지 하이웨스트로"
      → "코디": {"하의":"데님 팬츠", "하의.핏":"와이드", "하의.허리":"하이"}
  아이템을 바꾸면 그 아이템에 붙는 속성만 쓸 수 있다. 목록에 적힌 조건을 지킨다.
  색은 "하의.색상" 처럼 따로 있고, 안 정하면 "자동"이라 색 조합 방침이 정한다.
- "추천"은 사용자가 **그대로 눌러서 보낼 수 있는 말** 2~4개.
  * 사용자가 말하는 투로 쓴다. ("좀 더 어리게", "코디 밝게", "대표컷 뽑아줘")
  * 14자 이내. 지금 상황에서 다음에 할 만한 것으로 고른다.
  * 아직 안 정한 게 많으면 채우는 쪽을, 거의 다 정했으면 뽑는 쪽을 권한다.
  * 네가 되물을 때는 **고를 수 있는 값 자체**를 넣는다.
    (예: "가방은 뭘로 할까요?" → 추천 ["검정 숄더백","캔버스 토트백","가방 없이"])
    그래야 사장님이 타이핑하지 않고 누르기만 하면 된다.
"""


def _trim(history):
    h = [m for m in (history or []) if isinstance(m, dict)
         and m.get("role") in ("user", "assistant") and m.get("content")]
    return h[-MAX_TURNS:]


def _state_text(state):
    """지금 화면에 잡혀 있는 설정. 상대적인 수정을 위해 함께 넘긴다."""
    state = state or {}
    parts = []
    for name, key in (("모델", "model"), ("코디", "styling")):
        d = {k: v for k, v in (state.get(key) or {}).items() if v and v != NONE}
        parts.append("%s: %s" % (name, json.dumps(d, ensure_ascii=False) if d else "아직 없음"))
    if state.get("kind"):
        parts.append("제품종류: %s" % state["kind"])
    poses = state.get("poses") or {}
    if poses:
        parts.append("포즈: " + json.dumps(poses, ensure_ascii=False))
    cuts = state.get("cuts") or []
    if cuts:
        parts.append("만들 컷: " + ", ".join(CUTS.get(c, c) for c in cuts))
    parts.append("대표컷 있음: %s" % ("예" if state.get("has_hero") else "아니오"))
    return "\n".join(parts)


# ------------------------------------------------------------- 정리
def _clean_axis(d, allowed):
    """목록에 없는 값은 버린다. AI 가 지어내도 화면에 들어가지 못하게."""
    out = {}
    for k, v in (d or {}).items():
        opts = allowed.get(k)
        if opts is None:
            continue
        if isinstance(v, list):
            got = [x for x in v if x in opts]
            if got:
                out[k] = got
        elif v in opts:
            out[k] = v
    return out


def _allowed_model():
    a = {}
    for g in mt.traits_json():
        for it in g["items"]:
            if it.get("type") == "text":
                a[it["key"]] = None          # 자유 입력 축은 아래에서 따로
            else:
                a[it["key"]] = set(it.get("options") or [])
    return {k: v for k, v in a.items() if v}


def _allowed_styling():
    a = {}
    for g in sy.traits_json()["groups"]:
        for it in g["items"]:
            a[it["key"]] = set(it.get("options") or [])
            for ax in (it.get("axes") or []):        # 하의.핏 같은 속성 칸
                a["%s.%s" % (it["key"], ax["key"])] = set(ax.get("options") or [])
    return a


def _allowed_pose():
    p = pt.traits_json()
    a = {"강조 부위": set(p["focus"]), "베이스 포즈": set(p["base"])}
    for g in p["groups"]:
        for it in g["items"]:
            a[it["label"]] = set(it.get("options") or [])
    return a


def tidy(raw):
    """AI 답을 화면에 넣어도 안전한 형태로 다듬는다."""
    if not isinstance(raw, dict):
        raise ValueError("답을 읽지 못했습니다.")
    model = _clean_axis(raw.get("모델"), _allowed_model())
    styling = _clean_axis(raw.get("코디"), _allowed_styling())

    kind = raw.get("제품종류")
    kind = kind if kind in sy.KIND_ORDER else ""

    poses, pa = {}, _allowed_pose()
    for cut, sel in (raw.get("포즈") or {}).items():
        if cut in POSE_CUTS and isinstance(sel, dict):
            got = _clean_axis(sel, pa)
            if got:
                poses[cut] = got

    cuts = [c for c in (raw.get("컷") or []) if c in POSE_CUTS]

    run = str(raw.get("실행") or "none")
    if run not in ("none", "hero", "rest") and not (
            run.startswith("cut:") and run[4:] in CUTS):
        run = "none"

    tips = []
    for t in (raw.get("추천") or [])[:6]:
        t = " ".join(str(t).split())[:24]
        if t and t not in tips:
            tips.append(t)

    say = str(raw.get("말") or "").strip() or "설정을 바꿨습니다."
    return {"say": say[:400], "model": model, "styling": styling, "kind": kind,
            "poses": poses, "cuts": cuts, "run": run, "tips": tips[:4]}


def reply(history, message, state, chat_fn):
    """chat_fn(system, user) -> dict. 화면에 바로 반영할 수 있는 결과를 돌려준다."""
    msg = str(message or "").strip()
    if not msg:
        raise ValueError("무엇을 바꿀지 적어주세요.")

    convo = ""
    for m in _trim(history):
        who = "사용자" if m["role"] == "user" else "도우미"
        convo += "%s: %s\n" % (who, str(m["content"])[:400])

    user = (
        "## 고를 수 있는 값 (여기 없는 값은 쓰지 말 것)\n" + catalog() +
        "\n\n## 지금 화면에 잡혀 있는 설정\n" + _state_text(state) +
        ("\n\n## 지금까지 대화\n" + convo if convo else "") +
        "\n\n## 사용자가 방금 한 말\n" + msg
    )
    return tidy(chat_fn(SYSTEM, user))


def catalog_size():
    return len(catalog())
