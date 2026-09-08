#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코디(스타일링) 선택표
=====================
제품 말고 "모델이 함께 입은 나머지"를 정한다.

핵심 원칙
---------
* 비워두면 무난한 기본값이 들어간다. 화면에 "기본 — 인디고 청바지" 처럼
  무엇이 들어갈지 그대로 적어 두므로 숨은 동작이 없다.
* 신경 쓰기 싫으면 "AI가 알아서" 를 고른다. 그 슬롯만 프롬프트에서 빠진다.
* 제품 종류에 따라 충돌하는 슬롯은 아예 보여주지 않는다.
  (제품이 원피스면 상의·하의 슬롯이 사라진다)
* 코디는 판매 상품이 아니다. 프롬프트 끝에 "제품을 가리지 말 것" 잠금을 건다.
"""

AUTO = "AI가 알아서"

# ------------------------------------------------------------- 제품 종류
# 종류: (표시 이름, 이 종류일 때 감출 슬롯)
KINDS = {
    "상의":      ["상의"],
    "하의":      ["하의"],
    "원피스":    ["상의", "하의", "이너"],
    "아우터":    ["아우터"],
    "세트(상하의)": ["상의", "하의", "이너"],
    "기타":      [],
}
KIND_ORDER = ["상의", "하의", "원피스", "아우터", "세트(상하의)", "기타"]

# 제품명으로 종류를 짐작한다 (앞에 있을수록 우선)
_KIND_HINT = [
    ("아우터", ("자켓", "재킷", "코트", "점퍼", "패딩", "가디건", "블레이저",
                "야상", "무스탕", "바람막이", "집업", "트렌치", "아우터",
                "jacket", "coat", "cardigan", "blazer", "parka")),
    ("원피스", ("원피스", "드레스", "점프수트", "롬퍼", "dress", "onepiece", "jumpsuit")),
    ("세트(상하의)", ("세트", "셋업", "투피스", "한벌", "set", "setup")),
    ("하의", ("바지", "팬츠", "청바지", "데님", "슬랙스", "스커트", "치마",
              "반바지", "쇼츠", "레깅스", "조거", "하의",
              "pants", "jeans", "skirt", "shorts", "slacks", "trouser")),
    ("상의", ("티셔츠", "티", "블라우스", "셔츠", "니트", "맨투맨", "후드",
              "스웨터", "탑", "나시", "슬리브리스", "크롭", "상의", "폴라", "터틀넥",
              "shirt", "blouse", "knit", "tee", "top", "hoodie", "sweater")),
]


def guess_kind(name):
    """제품명으로 종류를 짐작한다. 못 찾으면 '상의' (가장 흔함)."""
    low = (name or "").lower()
    for kind, keys in _KIND_HINT:
        if any(k in low for k in keys):
            return kind
    return "상의"


def hidden_slots(kind):
    return list(KINDS.get(kind) or [])


# ------------------------------------------------------------- 슬롯 표
# 각 항목: 한글 라벨 -> 영어 조각. 첫 항목이 기본값이다.
def _slot(key, label, pairs, wide=False):
    return {"key": key, "label": label, "wide": wide,
            "options": [p[0] for p in pairs] + [AUTO],
            "default": pairs[0][0],
            "table": dict(pairs)}


TOP = _slot("상의", "상의", [
    ("기본 — 흰 반팔 티셔츠", "a plain white crew-neck T-shirt"),
    ("흰 셔츠", "a crisp white button-up shirt"),
    ("검정 반팔 티셔츠", "a plain black T-shirt"),
    ("검정 슬리브리스", "a simple black sleeveless top"),
    ("아이보리 니트", "a fine-gauge ivory knit top"),
    ("회색 맨투맨", "a plain grey sweatshirt"),
    ("스트라이프 긴팔", "a navy-and-white striped long-sleeve top"),
    ("검정 터틀넥", "a slim black turtleneck"),
    ("흰 크롭 티", "a short white cropped T-shirt"),
])

BOTTOM = _slot("하의", "하의", [
    ("기본 — 인디고 청바지", "straight-leg indigo denim jeans"),
    ("연청 와이드 데님", "light-wash wide-leg denim jeans"),
    ("진청 스키니", "dark-wash skinny jeans"),
    ("검정 슬랙스", "tailored black slacks"),
    ("베이지 치노", "beige chino trousers"),
    ("흰 와이드 팬츠", "white wide-leg trousers"),
    ("회색 트레이닝 팬츠", "grey jersey track pants"),
    ("데님 쇼츠", "light denim shorts"),
    ("검정 미니스커트", "a plain black mini skirt"),
    ("플리츠 롱스커트", "a pleated midi skirt"),
    ("검정 레깅스", "plain black leggings"),
])

OUTER = _slot("아우터", "아우터", [
    ("없음", ""),
    ("데님 재킷", "an unbuttoned light denim jacket"),
    ("검정 블레이저", "an open black tailored blazer"),
    ("베이지 트렌치", "an open beige trench coat"),
    ("회색 가디건", "an open grey cardigan"),
    ("크림 니트 가디건", "an open cream knit cardigan"),
    ("검정 레더 재킷", "an open black leather jacket"),
    ("회색 후드 집업", "an unzipped grey hooded zip-up"),
    ("네이비 롱 코트", "an open navy long coat"),
])

INNER = _slot("이너", "이너 · 레이어드", [
    ("없음", ""),
    ("흰 이너 티", "a thin white T-shirt layered underneath"),
    ("검정 이너 티", "a thin black T-shirt layered underneath"),
    ("흰 터틀넥", "a thin white turtleneck layered underneath"),
])

SHOES = _slot("신발", "신발", [
    ("기본 — 흰 스니커즈", "clean white low-top sneakers"),
    ("검정 스니커즈", "black low-top sneakers"),
    ("검정 로퍼", "black leather loafers"),
    ("앵클 부츠", "black ankle boots"),
    ("롱 부츠", "black knee-high boots"),
    ("검정 힐", "plain black heels"),
    ("누드 힐", "nude pointed heels"),
    ("샌들", "simple flat sandals"),
    ("플랫 슈즈", "plain ballet flats"),
    ("워커", "chunky black lace-up boots"),
    ("맨발", "bare feet"),
])

SOCKS = _slot("양말", "양말 · 스타킹", [
    ("안 보이게", ""),
    ("흰 양말", "short white socks"),
    ("검정 양말", "short black socks"),
    ("검정 스타킹", "sheer black tights"),
    ("살구 스타킹", "sheer nude tights"),
    ("니 삭스", "white knee-high socks"),
])

BAG = _slot("가방", "가방", [
    ("없음", ""),
    ("검정 숄더백", "a small black shoulder bag"),
    ("가죽 크로스백", "a compact leather cross-body bag"),
    ("캔버스 토트백", "a plain canvas tote bag"),
    ("미니백", "a tiny structured handbag"),
    ("백팩", "a simple backpack"),
    ("클러치", "a slim clutch held in one hand"),
])

ACC = {"key": "액세서리", "label": "액세서리 (여러 개 고를 수 있음)", "wide": True,
       "type": "multi",
       "table": {
           "얇은 골드 목걸이": "a thin gold necklace",
           "실버 체인 목걸이": "a fine silver chain necklace",
           "작은 스터드 귀걸이": "small stud earrings",
           "링 귀걸이": "small hoop earrings",
           "가는 반지": "a slim ring",
           "얇은 팔찌": "a thin bracelet",
           "손목시계": "a simple wristwatch",
           "가죽 벨트": "a narrow leather belt",
           "볼캡": "a plain baseball cap",
           "버킷햇": "a plain bucket hat",
           "베레모": "a wool beret",
           "안경": "clear-lens glasses",
           "선글라스": "slim sunglasses",
           "실크 스카프": "a small silk neck scarf",
           "헤어핀": "a minimal hair clip",
       }}
ACC["options"] = list(ACC["table"].keys())

COLOR = _slot("색조합", "색 조합 방침", [
    ("기본 — 무채색으로 받쳐주기",
     "Keep every styling piece in neutral black, white, grey, beige or plain denim so the "
     "product is the only real colour in the frame."),
    ("톤온톤 (제품과 같은 계열)",
     "Put the styling pieces in the same hue family as the product, one or two shades "
     "lighter or darker, for a tonal look."),
    ("제품 색이 튀게 대비",
     "Put the styling pieces in a restrained contrasting colour so the product reads as the "
     "brightest, most eye-catching item in the frame."),
    ("따뜻한 뉴트럴 (베이지·크림)",
     "Keep the styling pieces in warm neutrals - beige, cream, camel, soft brown."),
])

SLOTS = [TOP, BOTTOM, INNER, OUTER, SHOES, SOCKS, BAG, ACC, COLOR]
BY_KEY = {s["key"]: s for s in SLOTS}

GROUPS = [
    {"title": "함께 입는 옷", "keys": ["상의", "하의", "이너", "아우터"]},
    {"title": "신발 · 소품", "keys": ["신발", "양말", "가방", "액세서리"]},
    {"title": "색 방침", "keys": ["색조합"]},
]

# 코디가 제품을 잡아먹지 못하게 막는 잠금
STYLING_LOCK = (
    "STYLING LOCK: the styling pieces above are NOT the product being sold. Keep every one of "
    "them plain, understated and free of prints, logos or lettering, so nothing competes with "
    "the product. Any outerwear is worn fully open and pushed back so the product underneath "
    "stays completely visible. Nothing - no bag, strap, hand, hair or accessory - may cover, "
    "overlap, or cast a shadow on the product. Add only the accessories listed and nothing "
    "else: no extra jewellery, watches, hats, belts or bags that were not named.")


# ------------------------------------------------------------- 조립
def compose(sel, kind=None):
    """선택한 코디를 영어 프롬프트 조각으로 만든다. sel 은 {슬롯: 값} 딕셔너리."""
    sel = sel or {}
    hide = set(hidden_slots(kind or sel.get("제품종류") or "기타"))
    worn, color = [], ""

    for slot in SLOTS:
        key = slot["key"]
        if key in hide or key == "색조합":
            continue
        val = sel.get(key, slot.get("default"))
        if key == "액세서리":
            picked = val if isinstance(val, list) else ([val] if val else [])
            worn += [slot["table"][p] for p in picked if p in slot["table"]]
            continue
        if not val or val == AUTO:
            continue
        frag = slot["table"].get(val, "")
        if frag:
            worn.append(frag)

    cval = sel.get("색조합", COLOR["default"])
    if cval and cval != AUTO:
        color = COLOR["table"].get(cval, "")

    if not worn and not color:
        return ""

    parts = []
    if worn:
        parts.append("STYLING: apart from the product itself, the model wears " +
                     _join(worn) + ".")
    if color:
        parts.append(color)
    parts.append(STYLING_LOCK)
    return " ".join(parts)


def _join(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]


def traits_json():
    """화면이 쓸 선택지 목록."""
    out = []
    for g in GROUPS:
        items = []
        for k in g["keys"]:
            s = BY_KEY[k]
            items.append({"key": s["key"], "label": s["label"],
                          "type": s.get("type", "select"),
                          "wide": s.get("wide", False),
                          "options": s["options"],
                          "default": s.get("default", "")})
        out.append({"title": g["title"], "items": items})
    return {"kinds": KIND_ORDER, "hide": KINDS, "groups": out}


def describe(sel, kind=None):
    return compose(sel, kind)
