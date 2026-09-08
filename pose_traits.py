#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
포즈 미시 선택 시스템
=====================
"시크한 포즈" 같은 애매한 프리셋 대신, 몸을 관절 단위로 쪼개서 조합한다.

  강조 부위  →  베이스 포즈  →  세부 조정
  (무엇을 보여줄지)  (큰 틀)      (관절 단위로 덮어쓰기)

· 고르지 않은 축은 문장에 넣지 않는다
· 베이스 포즈는 세부 축들의 묶음일 뿐이라, 고른 뒤 원하는 관절만 바꾸면 된다
"""

import re

NONE = "지정 안 함"


def _o(pairs):
    d = {NONE: ""}
    for k, v in pairs:
        d[k] = v
    return d


# ============================================================ 몸통·하체
BODY_DIR = _o([
    ("정면", "squared to the camera"),
    ("좌 15°", "turned 15 degrees to their left"),
    ("우 15°", "turned 15 degrees to their right"),
    ("좌 30°", "turned 30 degrees to their left"),
    ("우 30°", "turned 30 degrees to their right"),
    ("좌 45°", "turned 45 degrees to their left"),
    ("우 45°", "turned 45 degrees to their right"),
    ("좌 측면", "in full left profile"),
    ("우 측면", "in full right profile"),
    ("좌 후면 45°", "turned 135 degrees to their left, back mostly to camera"),
    ("우 후면 45°", "turned 135 degrees to their right, back mostly to camera"),
    ("후면", "with the back fully to the camera"),
])
TORSO_TWIST = _o([
    ("하체와 동일", "torso aligned with the hips"),
    ("좌로 살짝 틀기", "torso turned slightly to their left"),
    ("우로 살짝 틀기", "torso turned slightly to their right"),
    ("좌로 크게 틀기", "torso turned well to their left"),
    ("우로 크게 틀기", "torso turned well to their right"),
])
TORSO_TILT = _o([
    ("수직", "spine upright"), ("앞으로 살짝", "leaning slightly forward"),
    ("뒤로 살짝", "leaning slightly back"),
    ("좌측 기울임", "tilted slightly to their left"),
    ("우측 기울임", "tilted slightly to their right"),
])
SHOULDERS = _o([
    ("수평", "shoulders level"), ("왼쪽 어깨 내림", "left shoulder dropped"),
    ("오른쪽 어깨 내림", "right shoulder dropped"),
    ("양 어깨 뒤로", "shoulders drawn back"), ("어깨 앞으로", "shoulders rolled slightly forward"),
])
WEIGHT = _o([
    ("양발 균등", "weight even on both feet"), ("왼발 중심", "weight on the left foot"),
    ("오른발 중심", "weight on the right foot"), ("앞발 중심", "weight on the front foot"),
    ("뒷발 중심", "weight on the back foot"),
])
FEET_GAP = _o([
    ("붙임", "feet together"), ("좁게", "feet close together"),
    ("어깨너비", "feet shoulder-width apart"), ("넓게", "feet set wide apart"),
])
LEG = [
    ("곧게", "straight"), ("살짝 굽힘", "slightly bent"), ("앞으로", "placed forward"),
    ("뒤로", "placed back"), ("옆으로", "set out to the side"),
    ("반대쪽과 교차", "crossed over the other"),
]
LEG_L = _o(LEG)
LEG_R = _o(LEG)
TOES = _o([
    ("정면", "toes pointing forward"), ("안쪽", "toes turned slightly inward"),
    ("바깥쪽", "toes turned outward"), ("한쪽만 바깥쪽", "one foot turned outward"),
])

# ============================================================ 팔·손
ARM = [
    ("자연스럽게 내림", "relaxed at the side"), ("살짝 굽힘", "slightly bent"),
    ("크게 굽힘", "bent sharply"), ("몸에서 벌림", "held away from the body"),
    ("뒤로", "drawn behind the body"),
]
ARM_L = _o(ARM)
ARM_R = _o(ARM)
HAND = [
    ("허벅지 옆", "resting beside the thigh"), ("허리", "on the waist"),
    ("골반", "on the hip"), ("앞주머니", "in a front pocket"),
    ("뒷주머니", "in a back pocket"), ("반대팔", "holding the opposite arm"),
    ("목", "touching the neck"), ("얼굴", "near the face"),
    ("머리", "in the hair"), ("의류", "touching the garment"),
]
HAND_L = _o(HAND)
HAND_R = _o(HAND)

# ============================================================ 고개·시선
HEAD_DIR = _o([
    ("정면", "head facing the camera"), ("좌 15°", "head turned 15 degrees left"),
    ("우 15°", "head turned 15 degrees right"), ("좌 30°", "head turned 30 degrees left"),
    ("우 30°", "head turned 30 degrees right"), ("측면", "head in profile"),
    ("뒤돌아봄", "head turned back over the shoulder"),
])
CHIN = _o([
    ("중립", "chin level"), ("살짝 들기", "chin raised slightly"),
    ("많이 들기", "chin raised high"), ("살짝 내리기", "chin lowered slightly"),
    ("많이 내리기", "chin dropped low"),
])
GAZE = _o([
    ("렌즈", "eyes on the lens"), ("좌측", "eyes looking off to the left"),
    ("우측", "eyes looking off to the right"), ("위", "eyes looking up"),
    ("아래", "eyes looking down"), ("먼 곳", "eyes on a distant point"),
    ("착용 의류", "eyes on the garment being worn"), ("눈 감음", "eyes closed"),
])

# ============================================================ 의류 접촉
COLLAR = _o([
    ("접촉 없음", "collar untouched"), ("한 손으로 잡기", "one hand holding the collar"),
    ("양손으로 잡기", "both hands holding the collar"),
    ("살짝 당기기", "the collar pulled lightly"), ("정리하기", "adjusting the collar"),
])
LAPEL = _o([
    ("한쪽 잡기", "one lapel held"), ("양쪽 잡기", "both lapels held"),
    ("살짝 펼치기", "the lapels opened slightly"),
])
FRONT = _o([
    ("그대로", "the front left as it falls"), ("한쪽 잡기", "one front panel held"),
    ("양쪽 잡기", "both front panels held"), ("벌리기", "the front held open"),
    ("여미기", "the front pulled closed"),
])
SLEEVE = _o([
    ("접촉 없음", "sleeves untouched"), ("소매 끝 잡기", "a cuff held between the fingers"),
    ("살짝 당기기", "a sleeve pulled lightly"), ("걷어 올리기", "a sleeve pushed up the forearm"),
    ("커프스 만지기", "adjusting the cuff"),
])
HEM = _o([
    ("그대로", "the hem left as it falls"), ("한쪽 잡기", "one side of the hem held"),
    ("양쪽 잡기", "both sides of the hem held"), ("살짝 당기기", "the hem pulled down lightly"),
    ("들어 올리기", "the hem lifted slightly"),
])
WAISTLINE = _o([
    ("접촉 없음", "the waist untouched"), ("허리선 잡기", "the waistline held"),
    ("밴딩 당기기", "the elastic waistband pulled lightly"),
    ("벨트 만지기", "a hand on the belt"),
])
POCKET = _o([
    ("사용 안 함", "pockets unused"), ("엄지만 넣기", "a thumb hooked into a pocket"),
    ("손 절반 넣기", "a hand half into a pocket"), ("손 전체 넣기", "a hand fully in a pocket"),
    ("양손 넣기", "both hands in the pockets"),
])
OUTER = _o([
    ("그대로", "the outer layer worn as it is"), ("열어두기", "the outer layer worn open"),
    ("한쪽 젖히기", "one side of the outer layer pushed back"),
    ("양쪽 펼치기", "the outer layer held open on both sides"),
    ("단추 잡기", "a hand on a button"), ("단추 잠그기", "fastening a button"),
    ("지퍼 잡기", "a hand on the zip pull"),
])
SKIRT = _o([
    ("그대로", "the skirt left as it falls"), ("한쪽 치맛단 잡기", "one side of the skirt held"),
    ("양쪽 치맛단 잡기", "both sides of the skirt held"),
    ("살짝 펼치기", "the skirt spread slightly"), ("턴하며 펼치기", "the skirt flaring in a turn"),
])

# ============================================================ 동작
MOTION = _o([
    ("정지", "standing still"), ("걷기 시작", "just starting to walk"),
    ("걷는 중", "mid-walk"), ("한 발 내딛기", "taking a single step"),
    ("몸 돌리기 시작", "starting to turn"), ("턴 중", "mid-turn"),
    ("뒤돌아보기", "turning to look back"), ("앉기 직전", "about to sit"),
    ("앉은 상태", "seated"), ("일어나기", "rising from a seat"),
    ("옷 정리하기", "adjusting the clothing"), ("소매 걷기", "rolling up a sleeve"),
    ("단추 잠그기", "doing up a button"), ("주머니에 손 넣는 중", "slipping a hand into a pocket"),
])
STRIDE = _o([("작게", "short steps"), ("보통", "an ordinary stride"), ("크게", "long strides")])
ENERGY = _o([
    ("거의 없음", "almost no movement"), ("자연스러움", "natural easy movement"),
    ("역동적", "dynamic energetic movement"),
])

# ============================================================ 강조 부위
FOCUS = {
    NONE: {"en": "", "hint": {}},
    "전체 실루엣": {"en": "the overall silhouette of the garment",
                "hint": {"몸 방향": "정면", "발 간격": "어깨너비", "왼팔": "몸에서 벌림",
                         "오른팔": "몸에서 벌림"}},
    "핏": {"en": "how the garment fits the body",
          "hint": {"몸 방향": "우 15°", "체중 중심": "오른발 중심"}},
    "어깨선": {"en": "the shoulder line and sleeve head",
             "hint": {"몸 방향": "우 30°", "어깨": "양 어깨 뒤로", "고개 방향": "좌 15°"}},
    "네크라인": {"en": "the neckline",
              "hint": {"고개 방향": "좌 15°", "턱": "살짝 들기", "왼손 위치": "목"}},
    "카라": {"en": "the collar",
            "hint": {"카라": "한 손으로 잡기", "턱": "살짝 내리기"}},
    "허리선": {"en": "the waistline",
             "hint": {"왼손 위치": "허리", "오른손 위치": "허리", "허리선": "허리선 잡기"}},
    "소매": {"en": "the sleeve and cuff",
            "hint": {"왼팔": "몸에서 벌림", "왼손 위치": "의류", "소매": "소매 끝 잡기"}},
    "커프스": {"en": "the cuff detail",
             "hint": {"왼팔": "크게 굽힘", "소매": "커프스 만지기"}},
    "밑단": {"en": "the hem finish",
            "hint": {"밑단": "한쪽 잡기", "시선": "아래"}},
    "주머니": {"en": "the pockets",
             "hint": {"주머니": "손 절반 넣기", "왼손 위치": "앞주머니"}},
    "힙라인": {"en": "the hip line and back fit",
             "hint": {"몸 방향": "우 후면 45°", "고개 방향": "뒤돌아봄"}},
    "허벅지 핏": {"en": "the fit through the thigh",
               "hint": {"몸 방향": "우 15°", "왼쪽 다리": "앞으로"}},
    "바지통": {"en": "the leg width and drape of the trousers",
             "hint": {"발 간격": "넓게", "동작": "걷는 중"}},
    "기장": {"en": "the overall length of the garment",
            "hint": {"몸 방향": "정면", "발 간격": "붙임"}},
    "뒷면": {"en": "the back of the garment",
            "hint": {"몸 방향": "후면", "고개 방향": "정면"}},
    "소재 움직임": {"en": "how the fabric moves",
                "hint": {"동작": "턴 중", "움직임 강도": "역동적"}},
}

# ============================================================ 베이스 포즈
BASE = {
    NONE: {},
    "기본 정면": {"몸 방향": "정면", "상체 기울기": "수직", "체중 중심": "양발 균등",
              "발 간격": "어깨너비", "왼팔": "자연스럽게 내림", "오른팔": "자연스럽게 내림",
              "왼손 위치": "허벅지 옆", "오른손 위치": "허벅지 옆", "고개 방향": "정면",
              "턱": "중립", "시선": "렌즈", "동작": "정지"},
    "자연스러운 짝다리": {"몸 방향": "우 15°", "체중 중심": "오른발 중심", "왼쪽 다리": "살짝 굽힘",
                   "오른쪽 다리": "곧게", "어깨": "왼쪽 어깨 내림", "왼팔": "자연스럽게 내림",
                   "오른팔": "살짝 굽힘", "오른손 위치": "골반", "고개 방향": "정면",
                   "시선": "렌즈", "동작": "정지"},
    "다리 교차": {"몸 방향": "우 15°", "체중 중심": "왼발 중심", "오른쪽 다리": "반대쪽과 교차",
              "발 간격": "붙임", "왼팔": "자연스럽게 내림", "오른팔": "살짝 굽힘",
              "고개 방향": "좌 15°", "턱": "살짝 내리기", "시선": "렌즈", "동작": "정지"},
    "워킹": {"몸 방향": "정면", "동작": "걷는 중", "보폭": "보통", "움직임 강도": "자연스러움",
           "왼팔": "살짝 굽힘", "오른팔": "살짝 굽힘", "고개 방향": "정면", "시선": "렌즈"},
    "뒤돌아보기": {"몸 방향": "우 후면 45°", "고개 방향": "뒤돌아봄", "시선": "렌즈",
              "체중 중심": "뒷발 중심", "왼팔": "자연스럽게 내림", "오른팔": "자연스럽게 내림",
              "동작": "뒤돌아보기"},
    "주머니 포즈": {"몸 방향": "우 15°", "체중 중심": "오른발 중심", "주머니": "손 절반 넣기",
              "왼손 위치": "앞주머니", "오른팔": "자연스럽게 내림", "고개 방향": "정면",
              "시선": "렌즈", "동작": "정지"},
    "의류 터치": {"몸 방향": "우 30°", "왼팔": "크게 굽힘", "왼손 위치": "의류",
              "오른팔": "자연스럽게 내림", "고개 방향": "좌 15°", "턱": "살짝 내리기",
              "시선": "착용 의류", "동작": "옷 정리하기"},
    "앉기": {"동작": "앉은 상태", "상체 기울기": "앞으로 살짝", "왼쪽 다리": "살짝 굽힘",
            "오른쪽 다리": "반대쪽과 교차", "왼손 위치": "허벅지 옆", "고개 방향": "정면",
            "시선": "렌즈"},
    "기대기": {"몸 방향": "우 30°", "상체 기울기": "뒤로 살짝", "체중 중심": "뒷발 중심",
            "왼쪽 다리": "곧게", "오른쪽 다리": "살짝 굽힘", "왼팔": "자연스럽게 내림",
            "오른손 위치": "골반", "고개 방향": "정면", "시선": "렌즈", "동작": "정지"},
}

# ============================================================ 축 정의
GROUPS = [
    ("몸통 · 하체", [
        ("몸 방향", BODY_DIR), ("상체 방향", TORSO_TWIST), ("상체 기울기", TORSO_TILT),
        ("어깨", SHOULDERS), ("체중 중심", WEIGHT), ("발 간격", FEET_GAP),
        ("왼쪽 다리", LEG_L), ("오른쪽 다리", LEG_R), ("발끝", TOES),
    ]),
    ("팔 · 손", [
        ("왼팔", ARM_L), ("오른팔", ARM_R), ("왼손 위치", HAND_L), ("오른손 위치", HAND_R),
    ]),
    ("고개 · 시선", [("고개 방향", HEAD_DIR), ("턱", CHIN), ("시선", GAZE)]),
    ("의류 접촉", [
        ("카라", COLLAR), ("라펠", LAPEL), ("앞섶", FRONT), ("소매", SLEEVE),
        ("밑단", HEM), ("허리선", WAISTLINE), ("주머니", POCKET),
        ("아우터", OUTER), ("스커트·원피스", SKIRT),
    ]),
    ("동작", [("동작", MOTION), ("보폭", STRIDE), ("움직임 강도", ENERGY)]),
]
TABLES = {label: table for _t, axes in GROUPS for label, table in axes}


def resolve(sel):
    """강조 부위 힌트 → 베이스 포즈 → 사용자가 직접 고른 값 순으로 덮어쓴다."""
    sel = dict(sel or {})
    out = {}
    focus = sel.get("강조 부위") or NONE
    out.update(BASE.get(sel.get("베이스 포즈") or NONE) or {})
    out.update((FOCUS.get(focus) or {}).get("hint") or {})   # 강조 부위가 베이스보다 우선
    for k, v in sel.items():
        if k in TABLES and v and v != NONE:
            out[k] = v
    return out, focus


def compose(sel):
    """고른 축들 → 영어 포즈 명세."""
    v, focus = resolve(sel)

    def g(k):
        return (TABLES.get(k) or {}).get(v.get(k) or "", "")

    parts = []
    body = [g(k) for k in ("몸 방향", "상체 방향", "상체 기울기", "어깨")]
    legs = [g(k) for k in ("체중 중심", "발 간격")]
    if g("왼쪽 다리"):
        legs.append("left leg " + g("왼쪽 다리"))
    if g("오른쪽 다리"):
        legs.append("right leg " + g("오른쪽 다리"))
    legs.append(g("발끝"))
    stance = [x for x in body + legs if x]
    if stance:
        parts.append("Body " + ", ".join(stance))

    arms = []
    if g("왼팔"):
        arms.append("left arm " + g("왼팔"))
    if g("오른팔"):
        arms.append("right arm " + g("오른팔"))
    if g("왼손 위치"):
        arms.append("left hand " + g("왼손 위치"))
    if g("오른손 위치"):
        arms.append("right hand " + g("오른손 위치"))
    if arms:
        parts.append(", ".join(arms))

    head = [g(k) for k in ("고개 방향", "턱", "시선")]
    head = [x for x in head if x]
    if head:
        parts.append(", ".join(head))

    touch = [g(k) for k in ("카라", "라펠", "앞섶", "소매", "밑단", "허리선",
                            "주머니", "아우터", "스커트·원피스")]
    touch = [x for x in touch if x]
    if touch:
        parts.append("Garment handling: " + ", ".join(touch))

    move = [g(k) for k in ("동작", "보폭", "움직임 강도")]
    move = [x for x in move if x]
    if move:
        parts.append("Movement: " + ", ".join(move))

    text = ""
    if parts:
        text = "POSE: " + ". ".join(parts) + "."
    fen = (FOCUS.get(focus) or {}).get("en") or ""
    if fen:
        text += (" " if text else "") + ("Compose the frame so %s is the most readable "
                                         "element of the image." % fen)
    return text


def traits_json():
    return {
        "focus": list(FOCUS.keys()),
        "base": list(BASE.keys()),
        "groups": [{"title": t, "items": [{"label": lab, "options": list(tab)}
                                          for lab, tab in axes]}
                   for t, axes in GROUPS],
    }
