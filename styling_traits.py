#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코디(스타일링) 선택표
=====================
제품 말고 "모델이 함께 입은 나머지"를 정한다.

왜 이렇게 나눴나
----------------
코디는 **파는 물건이 아니라 배경**이다. 그래서 고르는 기준은 "무슨 옷이냐"가
아니라 **사진에서 실루엣이 실제로 달라지느냐**여야 한다.

    소재(코튼/린넨/레이온) — 생성 결과에서 구분이 거의 안 된다 → 안 쓴다
    핏·기장·허리 위치·착용 방식 — 실루엣이 바로 달라진다 → 축으로 뺀다

그래서 한 칸을 세 겹으로 나눈다.

    대분류  →  아이템        →  속성
    데님       데님 팬츠        핏 와이드 · 기장 크롭 · 허리 하이 · 색 연청

아이템 이름에 핏과 색을 박아 넣지 않는 이유가 여기 있다.
"검정 와이드 슬랙스"를 하나의 값으로 두면 색 하나 바꾸려고 항목을 또 만들어야
한다. 슬랙스 하나에 핏 5 × 기장 4 × 허리 3 × 색 14 = 840가지가 이미 들어 있다.
아이템은 125개뿐이지만 한 벌로 조합할 수 있는 코디는 천문학적이다.
(count_combos() 로 세어 볼 수 있다)

선택은 단계적으로 좁아지므로, 드롭다운 하나에 수십 개를 박아 두는 것보다
고르기 쉽다. 아무것도 안 건드리면 각 축의 첫 값(무난한 기본)이 들어간다.

그 밖의 원칙
------------
* 신경 쓰기 싫으면 색을 "자동"으로 둔다. 그 자리는 아래 '색 조합 방침'이 정한다.
* 제품 종류에 따라 충돌하는 칸은 아예 보여주지 않는다. (원피스면 상의·하의가 사라짐)
* 코디는 판매 상품이 아니다. 프롬프트 끝에 "제품을 가리지 말 것" 잠금을 건다.
"""

AUTO = "AI가 알아서"

# ------------------------------------------------------------- 제품 종류
KINDS = {
    "상의":      ["상의"],
    "하의":      ["하의"],
    "원피스":    ["상의", "하의", "이너"],
    "아우터":    ["아우터"],
    "세트(상하의)": ["상의", "하의", "이너"],
    "기타":      [],
}
KIND_ORDER = ["상의", "하의", "원피스", "아우터", "세트(상하의)", "기타"]

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
    low = (name or "").lower()
    for kind, keys in _KIND_HINT:
        if any(k in low for k in keys):
            return kind
    return "상의"


def hidden_slots(kind):
    return list(KINDS.get(kind) or [])


# ============================================================== 속성 축
# 각 축: 첫 값이 기본. 영어 조각이 ""면 프롬프트에 아무것도 안 붙는다.
def _ax(key, label, pairs, where="adj", ord=5):
    """where: adj = 명사 앞 형용사, tail = 문장 뒤 절
    ord  : 형용사를 붙이는 순서. 영어는 허리 > 핏 > 기장 > 색 순이 자연스럽다."""
    return {"key": key, "label": label, "where": where, "ord": ord,
            "options": [p[0] for p in pairs],
            "default": pairs[0][0], "table": dict(pairs)}


FIT_TOP = _ax("핏", "핏", [
    ("레귤러", "regular-fit"), ("슬림", "slim-fit"),
    ("루즈", "relaxed-fit"), ("오버", "oversized"),
], ord=2)
LEN_TOP = _ax("기장", "기장", [
    ("기본", ""), ("크롭", "waist-cropped"), ("롱", "hip-length"),
], ord=3)
TUCK = _ax("착용", "착용 방식", [
    ("빼 입기", "worn untucked"),
    ("넣어 입기", "tucked into the bottoms"),
    ("앞만 넣기", "front-tucked into the bottoms at the centre only"),
], where="tail")

FIT_BTM = _ax("핏", "핏", [
    ("레귤러", "straight-leg"), ("스키니", "skinny"), ("슬림", "slim-fit"),
    ("루즈", "relaxed-fit"), ("와이드", "wide-leg"),
], ord=2)
LEN_BTM = _ax("기장", "기장", [
    ("기본", "full-length"), ("크롭", "ankle-cropped"),
    ("앵클", "ankle-length"), ("롱", "floor-length"),
], ord=3)
LEN_SKIRT = _ax("기장", "기장", [
    ("미디", "midi-length"), ("미니", "mini-length"), ("롱", "maxi-length"),
], ord=3)
RISE = _ax("허리", "허리 위치", [
    ("미드", "mid-rise"), ("하이", "high-waisted"), ("로우", "low-rise"),
], ord=1)

FIT_OUT = _ax("핏", "핏", [
    ("레귤러", "regular-fit"), ("슬림", "slim-fit"), ("오버", "oversized"),
], ord=2)
LEN_OUT = _ax("기장", "기장", [
    ("기본", "hip-length"), ("크롭", "cropped"),
    ("롱", "knee-length"), ("맥시", "ankle-length"),
], ord=3)

_COLORS = [
    ("자동", ""), ("화이트", "white"), ("아이보리", "ivory"), ("베이지", "beige"),
    ("브라운", "brown"), ("카키", "khaki"), ("그레이", "grey"), ("차콜", "charcoal"),
    ("블랙", "black"), ("네이비", "navy"), ("블루", "blue"), ("버건디", "burgundy"),
    ("파스텔", "soft pastel"), ("비비드", "vivid"),
]
COLOR_AX = _ax("색상", "색", _COLORS, ord=4)
COLOR_DENIM = _ax("색상", "워시", [
    ("자동", ""), ("연청", "light-wash"), ("중청", "mid-wash"),
    ("진청", "dark-wash"), ("흑청", "black-wash"), ("화이트", "white"),
    ("그레이", "grey"),
], ord=4)

TOP_AX = [FIT_TOP, LEN_TOP, COLOR_AX, TUCK]
BTM_AX = [FIT_BTM, LEN_BTM, RISE, COLOR_AX]
DENIM_AX = [FIT_BTM, LEN_BTM, RISE, COLOR_DENIM]
SKIRT_AX = [LEN_SKIRT, RISE, COLOR_AX]
SHORTS_AX = [FIT_BTM, RISE, COLOR_AX]
OUT_AX = [FIT_OUT, LEN_OUT, COLOR_AX]
COLOR_ONLY = [COLOR_AX]


# ============================================================== 아이템 표
# (한글, 영어, 복수형인가)
def _slot(key, label, cats, kind="cascade"):
    """대분류마다 붙는 속성 축이 다르다. 같은 이름의 축이라도 값 목록이 다르면
    (하의.기장 = 팬츠는 기본/크롭/앵클/롱, 스커트는 미디/미니/롱) 대분류별로
    따로 들고 있어야 한다. 그래서 축을 대분류 안에 통째로 넣는다."""
    table, out, flat, nones = {}, [], [], []
    for title, attrs, items in cats:
        names = []
        for it in items:
            ko, en = it[0], it[1]
            pl = it[2] if len(it) > 2 else False
            table[ko] = (en, pl)
            names.append(ko)
            flat.append(ko)
            if not en:
                nones.append(ko)
        out.append({"title": title, "options": names, "axes": list(attrs)})
    # 검증·안내용: 같은 축 이름이 여러 번 나오면 값을 합쳐 둔다
    union = {}
    for _t, attrs, _i in cats:
        for a in attrs:
            u = union.setdefault(a["key"], {"key": a["key"], "label": a["label"],
                                            "options": [], "default": a["default"]})
            for o in a["options"]:
                if o not in u["options"]:
                    u["options"].append(o)
    return {"key": key, "label": label, "type": kind, "wide": True,
            "cats": out, "axes": list(union.values()), "options": flat, "none": nones,
            "default": cats[0][2][0][0], "table": table}


TOP = _slot("상의", "상의", [
    ("티셔츠", TOP_AX, [
        ("반팔 티셔츠", "short-sleeve T-shirt"),
        ("긴팔 티셔츠", "long-sleeve T-shirt"),
        ("민소매 티셔츠", "sleeveless top"),
        ("탱크톱", "tank top"),
        ("폴로 셔츠", "polo shirt"),
    ]),
    ("셔츠 · 블라우스", TOP_AX, [
        ("셔츠", "button-up shirt"),
        ("반팔 셔츠", "short-sleeve button-up shirt"),
        ("오픈카라 셔츠", "open-collar camp shirt"),
        ("데님 셔츠", "denim shirt"),
        ("블라우스", "blouse"),
        ("타이 블라우스", "tie-neck blouse"),
    ]),
    ("니트", TOP_AX, [
        ("라운드넥 니트", "crew-neck knit top"),
        ("V넥 니트", "V-neck knit top"),
        ("터틀넥", "turtleneck knit top"),
        ("반팔 니트", "short-sleeve knit top"),
        ("니트 베스트", "sleeveless knit vest"),
    ]),
    ("스웨트", TOP_AX, [
        ("맨투맨", "sweatshirt"),
        ("후드티", "pullover hoodie"),
    ]),
])

BOTTOM = _slot("하의", "하의", [
    ("데님", DENIM_AX, [
        ("데님 팬츠", "denim jeans", True),
        ("부츠컷 데님", "boot-cut denim jeans", True),
        ("배기 데님", "baggy denim jeans", True),
        ("카고 데님", "denim cargo pants", True),
        ("데님 쇼츠", "denim shorts", True),
        ("데님 스커트", "denim skirt"),
    ]),
    ("팬츠", BTM_AX, [
        ("슬랙스", "tailored trousers", True),
        ("부츠컷 슬랙스", "boot-cut tailored trousers", True),
        ("테이퍼드 슬랙스", "tapered tailored trousers", True),
        ("치노 팬츠", "chino trousers", True),
        ("코튼 팬츠", "cotton trousers", True),
        ("카고 팬츠", "cargo trousers", True),
        ("코듀로이 팬츠", "corduroy trousers", True),
        ("조거 팬츠", "jogger pants", True),
        ("트레이닝 팬츠", "track pants", True),
        ("레깅스", "leggings", True),
    ]),
    ("스커트", SKIRT_AX, [
        ("A라인 스커트", "A-line skirt"),
        ("H라인 스커트", "straight pencil skirt"),
        ("플리츠 스커트", "pleated skirt"),
        ("플레어 스커트", "flared skirt"),
        ("머메이드 스커트", "mermaid-cut skirt"),
        ("니트 스커트", "knit skirt"),
    ]),
    ("쇼츠", SHORTS_AX, [
        ("코튼 쇼츠", "cotton shorts", True),
        ("슬랙스 쇼츠", "tailored shorts", True),
        ("버뮤다 팬츠", "bermuda shorts", True),
        ("트레이닝 쇼츠", "jersey shorts", True),
        ("바이커 쇼츠", "fitted biker shorts", True),
    ]),
])

OUTER = _slot("아우터", "아우터", [
    ("안 걸침", [], [("아우터 없음", "")]),
    ("재킷", OUT_AX, [
        ("블레이저", "tailored blazer"),
        ("트위드 재킷", "tweed jacket"),
        ("데님 재킷", "denim jacket"),
        ("레더 재킷", "leather jacket"),
        ("봄버 재킷", "bomber jacket"),
        ("바시티 재킷", "varsity jacket"),
    ]),
    ("코트", OUT_AX, [
        ("트렌치코트", "trench coat"),
        ("싱글 코트", "single-breasted coat"),
        ("더블 코트", "double-breasted coat"),
    ]),
    ("니트 아우터", OUT_AX, [
        ("가디건", "cardigan"),
        ("케이블 가디건", "cable-knit cardigan"),
        ("니트 집업", "knit zip-up"),
    ]),
    ("캐주얼 · 방한", OUT_AX, [
        ("후드 집업", "zip-up hoodie"),
        ("바람막이", "windbreaker"),
        ("플리스", "fleece jacket"),
        ("패딩 베스트", "quilted puffer vest"),
        ("패딩 점퍼", "quilted puffer jacket"),
    ]),
])

INNER = _slot("이너", "이너 · 레이어드", [
    ("안 겹쳐 입음", [], [("이너 없음", "")]),
    ("기본", COLOR_ONLY, [
        ("반팔 이너 티", "short-sleeve T-shirt layered underneath"),
        ("긴팔 이너 티", "long-sleeve T-shirt layered underneath"),
        ("민소매 이너", "sleeveless top layered underneath"),
        ("이너 탱크톱", "tank top layered underneath"),
    ]),
    ("레이어드", COLOR_ONLY, [
        ("이너 셔츠", "button-up shirt layered underneath, collar and cuffs showing"),
        ("스트라이프 셔츠", "striped button-up shirt layered underneath"),
        ("이너 터틀넥", "turtleneck layered underneath"),
        ("하이넥", "high-neck top layered underneath"),
        ("얇은 니트", "fine-gauge knit top layered underneath"),
    ]),
])

SHOES = _slot("신발", "신발", [
    ("스니커즈", COLOR_ONLY, [
        ("로우탑 스니커즈", "low-top sneakers", True),
        ("하이탑 스니커즈", "high-top sneakers", True),
        ("러닝화", "running shoes", True),
        ("청키 스니커즈", "chunky platform sneakers", True),
        ("캔버스화", "canvas sneakers", True),
    ]),
    ("로퍼 · 구두", COLOR_ONLY, [
        ("페니로퍼", "penny loafers", True),
        ("청키 로퍼", "chunky-sole loafers", True),
        ("옥스퍼드", "oxford shoes", True),
        ("더비슈즈", "derby shoes", True),
        ("플랫슈즈", "ballet flats", True),
        ("메리제인", "Mary Jane shoes", True),
    ]),
    ("힐", COLOR_ONLY, [
        ("펌프스", "pointed pumps", True),
        ("슬링백", "slingback heels", True),
        ("키튼힐", "kitten heels", True),
        ("플랫폼힐", "platform heels", True),
        ("스트랩힐", "strappy heels", True),
    ]),
    ("부츠", COLOR_ONLY, [
        ("앵클부츠", "ankle boots", True),
        ("첼시부츠", "chelsea boots", True),
        ("워커", "chunky lace-up boots", True),
        ("미들부츠", "mid-calf boots", True),
        ("롱부츠", "knee-high boots", True),
        ("웨스턴부츠", "western boots", True),
    ]),
    ("샌들", COLOR_ONLY, [
        ("슬라이드", "slide sandals", True),
        ("스트랩 샌들", "thin-strap sandals", True),
        ("스포츠 샌들", "sport sandals", True),
        ("플랫폼 샌들", "platform sandals", True),
        ("뮬", "backless mules", True),
    ]),
    ("신발 없음", [], [("맨발", "bare feet", True)]),
])

SOCKS = _slot("양말", "양말 · 스타킹", [
    ("안 보이게", [], [("양말 안 보임", "")]),
    ("길이", COLOR_ONLY, [
        ("페이크삭스", "no-show socks", True),
        ("발목양말", "ankle socks", True),
        ("크루삭스", "crew socks", True),
        ("미드카프", "mid-calf socks", True),
        ("니삭스", "knee-high socks", True),
        ("오버니삭스", "over-the-knee socks", True),
    ]),
    ("스타킹", [], [
        ("살색 스타킹", "sheer nude tights", True),
        ("검정 시스루", "sheer black tights", True),
        ("검정 불투명", "opaque black tights", True),
        ("컬러 타이츠", "coloured opaque tights", True),
    ]),
])

BAG = _slot("가방", "가방", [
    ("안 듦", [], [("가방 없음", "")]),
    ("숄더", COLOR_ONLY, [
        ("미니 숄더백", "mini shoulder bag"),
        ("숄더백", "shoulder bag"),
        ("호보백", "slouchy hobo bag"),
        ("버킷백", "bucket bag"),
    ]),
    ("크로스", COLOR_ONLY, [
        ("미니 크로스백", "mini cross-body bag"),
        ("크로스백", "cross-body bag"),
        ("메신저백", "messenger bag"),
    ]),
    ("손에 드는 것", COLOR_ONLY, [
        ("토트백", "tote bag"),
        ("미니 토트백", "mini tote bag"),
        ("클러치", "clutch"),
    ]),
    ("기타", COLOR_ONLY, [
        ("백팩", "backpack"),
        ("에코백", "canvas eco bag"),
    ]),
])

# 액세서리는 여러 개를 동시에 다는 칸이라 속성 층을 두지 않는다
ACC = {"key": "액세서리", "label": "액세서리 (여러 개 고를 수 있음)", "wide": True,
       "type": "multi", "axes": [], "none": [],
       "optgroups": [], "options": [], "table": {}}
for _t, _pairs in [
    ("목", [("얇은 목걸이", "a thin necklace"),
            ("펜던트 목걸이", "a small pendant necklace"),
            ("체인 목걸이", "a chain necklace"),
            ("초커", "a plain choker"),
            ("진주 목걸이", "a pearl necklace"),
            ("스카프", "a small silk neck scarf")]),
    ("귀", [("스터드 귀걸이", "stud earrings"),
            ("링 귀걸이", "hoop earrings"),
            ("드롭 귀걸이", "slim drop earrings"),
            ("진주 귀걸이", "pearl earrings")]),
    ("손 · 손목", [("메탈 시계", "a metal-band watch"),
                  ("가죽 시계", "a leather-strap watch"),
                  ("스마트워치", "a smartwatch"),
                  ("얇은 팔찌", "a thin bracelet"),
                  ("체인 팔찌", "a chain bracelet"),
                  ("반지", "a slim ring")]),
    ("머리", [("볼캡", "a plain baseball cap"),
              ("비니", "a knit beanie"),
              ("버킷햇", "a plain bucket hat"),
              ("헤어밴드", "a fabric headband"),
              ("헤어핀", "a minimal hair clip"),
              ("리본", "a hair ribbon")]),
    ("얼굴", [("안경", "clear-lens glasses"),
              ("선글라스", "slim sunglasses")]),
    ("허리", [("얇은 벨트", "a thin belt"),
              ("기본 가죽벨트", "a leather belt"),
              ("와이드 벨트", "a wide belt"),
              ("체인 벨트", "a slim chain belt")]),
]:
    ACC["optgroups"].append({"title": _t, "options": [p[0] for p in _pairs]})
    for _ko, _en in _pairs:
        ACC["table"][_ko] = _en
        ACC["options"].append(_ko)

# ------------------------------------------------------------- 색 조합 방침
COLOR = {"key": "색조합", "label": "색 조합 방침", "wide": True, "type": "select",
         "axes": [], "none": [], "optgroups": [], "options": [], "table": {}}
for _t, _pairs in [
    ("제품을 살리는 쪽", [
        ("제품 중심 뉴트럴",
         "Restrict every styling piece to white, black, grey or beige so the product is the "
         "only real colour in the frame."),
        ("뉴트럴 + 포인트",
         "Keep the clothing in neutral tones and put one single accent colour on exactly one "
         "small item - the bag or the shoes - never on a piece next to the product."),
        ("보색 포인트",
         "Use one restrained colour that sits opposite the product on the colour wheel, on a "
         "single small item only, so the product reads as the brightest thing in the frame."),
        ("고대비",
         "Make the top and the bottom clearly different in lightness - one light, one dark - so "
         "the silhouette separates cleanly."),
    ]),
    ("한 계열로 묶는 쪽", [
        ("톤온톤",
         "Keep every styling piece in the same hue as the product and vary only lightness and "
         "saturation."),
        ("유사색",
         "Use colours that sit next to each other on the colour wheel, close to the product's "
         "hue but not identical."),
        ("모노크롬",
         "Build the whole outfit from one single colour family, head to toe."),
        ("제품색 반복",
         "Repeat the product's own colour on exactly one other item so the eye travels between "
         "the two."),
        ("저채도",
         "Keep every styling piece muted and low in saturation - dusty, washed-out tones with "
         "no bright colour anywhere."),
    ]),
    ("한 가지 색으로", [
        ("화이트 중심",
         "Keep most styling pieces white or ivory, with at most one darker neutral item."),
        ("블랙 중심",
         "Keep most styling pieces black or charcoal, with at most one lighter neutral item."),
        ("올블랙", "Make every single styling piece black."),
        ("올화이트", "Make every single styling piece white or ivory."),
    ]),
]:
    COLOR["optgroups"].append({"title": _t, "options": [p[0] for p in _pairs]})
    for _ko, _en in _pairs:
        COLOR["table"][_ko] = _en
        COLOR["options"].append(_ko)
COLOR["default"] = "제품 중심 뉴트럴"
COLOR["optgroups"].append({"title": "", "options": [AUTO]})
COLOR["options"].append(AUTO)

ACC["default"] = ""

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


# ============================================================== 조립
def attr_key(slot_key, axis_key):
    """화면·저장에 쓰는 속성 칸 이름. 예: '하의.핏'"""
    return "%s.%s" % (slot_key, axis_key)


def _axes_for(slot, item):
    """그 아이템에 실제로 붙는 속성 축만 돌려준다."""
    for cat in slot["cats"]:
        if item in cat["options"]:
            return list(cat["axes"])
    return []


def _article(phrase):
    return "an " if phrase[:1].lower() in "aeiou" else "a "


def _phrase(slot, sel):
    """아이템 + 속성을 영어 한 조각으로."""
    item = sel.get(slot["key"], slot.get("default"))
    if not item or item == AUTO or item in slot["none"]:
        return ""
    got = slot["table"].get(item)
    if not got:
        # 예전 판으로 저장해 둔 이름이면 그 칸의 기본값으로 대신한다 (통째로 비우지 않는다)
        item = slot.get("default")
        if not item or item in slot["none"]:
            return ""
        got = slot["table"].get(item)
        if not got:
            return ""
    en, plural = got
    if not en:
        return ""

    adj, tail = [], []
    for ax in sorted(_axes_for(slot, item), key=lambda a: a.get("ord", 5)):
        val = sel.get(attr_key(slot["key"], ax["key"]), ax["default"])
        frag = ax["table"].get(val, "")
        if not frag:
            continue
        (tail if ax["where"] == "tail" else adj).append(frag)

    body = " ".join(adj + [en])
    if not plural:
        body = _article(body) + body
    if tail:
        body += ", " + " and ".join(tail)
    return body


def compose(sel, kind=None):
    """선택한 코디를 영어 프롬프트 조각으로 만든다."""
    sel = sel or {}
    hide = set(hidden_slots(kind or sel.get("제품종류") or "기타"))
    worn, color = [], ""

    for slot in SLOTS:
        key = slot["key"]
        if key in hide or key == "색조합":
            continue
        if key == "액세서리":
            val = sel.get(key)
            picked = val if isinstance(val, list) else ([val] if val else [])
            worn += [slot["table"][p] for p in picked if p in slot["table"]]
            continue
        frag = _phrase(slot, sel)
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
    if len(items) == 2:
        return items[0] + " and " + items[1]
    return "; ".join(items[:-1]) + "; and " + items[-1]


def traits_json():
    """화면이 쓸 선택지 목록."""
    out = []
    for g in GROUPS:
        items = []
        for k in g["keys"]:
            s = BY_KEY[k]
            it = {"key": s["key"], "label": s["label"], "type": s.get("type", "select"),
                  "wide": s.get("wide", False), "options": s["options"],
                  "none": s.get("none") or [], "default": s.get("default", "")}
            if s.get("type") == "cascade":
                it["cats"] = [{"title": c["title"], "options": c["options"],
                               "axes": [{"key": a["key"], "label": a["label"],
                                         "options": a["options"], "default": a["default"]}
                                        for a in c["axes"]]} for c in s["cats"]]
                it["axes"] = [{"key": a["key"], "label": a["label"],
                               "options": a["options"], "default": a["default"]}
                              for a in s["axes"]]
            else:
                it["optgroups"] = s.get("optgroups") or []
            items.append(it)
        out.append({"title": g["title"], "items": items})
    return {"kinds": KIND_ORDER, "hide": KINDS, "groups": out}


def describe(sel, kind=None):
    return compose(sel, kind)


def count_combos():
    """아이템 × 속성으로 만들 수 있는 조합 수 (안내문에 쓴다)."""
    total = 1
    for slot in SLOTS:
        if slot.get("type") != "cascade":
            continue
        n = 0
        for cat in slot["cats"]:
            per = 1
            for a in cat["axes"]:
                per *= len(a["options"])
            n += len(cat["options"]) * per
        total *= max(n, 1)
    return total
