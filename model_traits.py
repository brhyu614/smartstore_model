#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모델 디테일 선택 시스템
=======================
관찰 가능한 속성을 축(axis)별로 고르면 영어 인물 묘사가 조립된다.

원칙
----
· 축끼리 의미가 겹치지 않게 나눈다 (피부색 ≠ 언더톤 ≠ 피부 표현)
· 고르지 않은 항목은 문장에 아예 넣지 않는다  ← 프롬프트가 길어지면 품질이 떨어진다
· 인상(사람이 어떻게 읽히는지)과 표정(그 순간)은 분리한다
· 외형과 역할(페르소나)도 분리한다
"""

import re

NONE = "지정 안 함"


def _o(pairs):
    """(한글, 영어) 목록 → {한글: 영어}. 맨 앞에 '지정 안 함' 을 넣는다."""
    d = {NONE: ""}
    for k, v in pairs:
        d[k] = v
    return d


# ============================================================ 1. 기본
SEX = {
    "여성": {"noun": "female", "poss": "her", "sub": "She"},
    "남성": {"noun": "male", "poss": "his", "sub": "He"},
    "중성적": {"noun": "androgynous", "poss": "their", "sub": "They"},
}
# "*" 로 시작하면 아동 모델 → 조립 규칙이 달라진다 (메이크업·수염 제외, 안전 문구 추가)
AGE = _o([
    ("아기 (6~12개월)", "*a baby around 9 months old"),
    ("유아 (1~3세)", "*a toddler around 2 years old"),
    ("아동 (4~6세)", "*a young child around 5 years old"),
    ("아동 (7~9세)", "*a child around 8 years old"),
    ("주니어 (10~12세)", "*a pre-teen around 11 years old"),
    ("20대 초반", "reads as being in their early 20s"),
    ("20대 중반", "reads as being in their mid 20s"),
    ("20대 후반", "reads as being in their late 20s"),
    ("30대 초반", "reads as being in their early 30s"),
    ("30대 중반", "reads as being in their mid 30s"),
    ("30대 후반", "reads as being in their late 30s"),
    ("40대", "reads as being in their 40s"),
    ("50대", "reads as being in their 50s"),
    ("60대", "reads as being in their 60s"),
    ("70대+", "reads as being in their 70s"),
])
REGION = _o([
    ("동아시아계", "East Asian"), ("한국계", "Korean"),
    ("동남아시아계", "Southeast Asian"), ("남아시아계", "South Asian"),
    ("중동계", "Middle Eastern"), ("유럽계", "European"),
    ("아프리카계", "Black African"), ("라틴계", "Latin American"),
    ("다인종 외형", "of mixed heritage"),
])

# ============================================================ 2. 키·체형
HEIGHT = _o([
    ("매우 작음", "noticeably short"), ("작은 편", "on the shorter side"),
    ("평균", "of average height"), ("큰 편", "on the taller side"),
    ("매우 큼", "strikingly tall"),
])
BODY = _o([
    ("매우 마른", "a very thin frame"), ("마른", "a lean thin frame"),
    ("슬림", "a slim build"), ("보통", "an average build"),
    ("탄탄한", "a firm solid build"), ("볼륨 있는", "a curvy full figure"),
    ("통통한", "a soft rounded build"), ("플러스 사이즈", "a plus-size body"),
])
MUSCLE = _o([
    ("거의 없음", "almost no visible muscle definition"),
    ("낮음", "soft low muscle definition"),
    ("보통", "ordinary muscle definition"),
    ("잔근육", "subtle wiry muscle definition"),
    ("탄탄함", "clearly toned muscles"),
    ("근육질", "well-developed muscles"),
    ("매우 근육질", "heavily built muscles"),
])
SHOULDER = _o([("좁음", "narrow shoulders"), ("보통", "average shoulders"),
               ("넓음", "broad shoulders")])
PROPORTION = _o([("상체가 긴 편", "a longer torso"), ("균형형", "balanced proportions"),
                 ("하체가 긴 편", "longer legs than torso")])
LIMBS = _o([("짧은 편", "shorter limbs"), ("평균", "average-length limbs"),
            ("긴 편", "long limbs")])

# ============================================================ 3. 피부
SKIN = _o([
    ("매우 밝음", "very fair skin"), ("밝음", "fair skin"),
    ("라이트 베이지", "light beige skin"), ("미디엄 베이지", "medium beige skin"),
    ("탄", "tan skin"), ("라이트 브라운", "light brown skin"),
    ("미디엄 브라운", "medium brown skin"), ("딥 브라운", "deep brown skin"),
    ("매우 짙음", "very deep skin"),
])
UNDERTONE = _o([
    ("쿨 핑크", "cool pink undertones"), ("쿨", "cool undertones"),
    ("뉴트럴", "neutral undertones"), ("웜", "warm undertones"),
    ("골든", "golden undertones"), ("올리브", "olive undertones"),
])
SKIN_TEXTURE = _o([
    ("매우 매끈", "very smooth even skin"),
    ("자연스러운 피부결", "natural skin texture"),
    ("모공이 보이는 자연 피부", "natural skin with visible pores"),
    ("주근깨", "freckled skin"), ("점 있음", "skin with a few small moles"),
    ("홍조", "a natural flush across the cheeks"),
    ("잡티 자연스럽게", "natural skin with light blemishes left visible"),
])
SKIN_FINISH = _o([
    ("Bare Skin", "bare untouched skin"), ("내추럴", "a natural skin finish"),
    ("글로우", "a glowing skin finish"), ("물광", "a dewy glass-skin finish"),
    ("세미매트", "a semi-matte skin finish"), ("매트", "a matte skin finish"),
    ("선키스드", "a sun-kissed tanned finish"),
])

# ============================================================ 4~9. 얼굴
FACE = _o([
    ("둥근형", "a round face"), ("계란형", "an egg-shaped face"),
    ("타원형", "an oval face"), ("긴형", "a long face"),
    ("하트형", "a heart-shaped face"), ("역삼각형", "an inverted-triangle face"),
    ("사각형", "a square face"), ("각진형", "an angular face"),
    ("다이아몬드형", "a diamond-shaped face"),
    ("광대가 도드라진형", "a face with prominent cheekbones"),
    ("턱선이 뚜렷한형", "a face with a sharply defined jawline"),
    ("갸름한형", "a slim tapered face"),
])
EYE_SIZE = _o([("작음", "small"), ("보통", "medium-sized"), ("큼", "large")])
# "~" 로 시작하면 eyes 뒤에 붙는 꼬리말
EYE_SHAPE = _o([
    ("둥근 눈", "round"), ("아몬드형", "almond-shaped"),
    ("가로로 긴 눈", "long and narrow"), ("세로로 큰 눈", "tall and open"),
    ("눈꼬리가 올라감", "~with upturned outer corners"),
    ("눈꼬리가 내려감", "~with downturned outer corners"),
    ("깊게 들어간 눈", "deep-set"),
])
EYELID = _o([
    ("무쌍", "monolids with no crease"), ("속쌍", "hidden inner double eyelids"),
    ("얇은 쌍꺼풀", "thin double eyelids"), ("뚜렷한 쌍꺼풀", "clearly defined double eyelids"),
])
IRIS = _o([
    ("블랙", "black irises"), ("다크브라운", "dark brown irises"),
    ("브라운", "brown irises"), ("라이트브라운", "light brown irises"),
    ("헤이즐", "hazel irises"), ("그린", "green irises"),
    ("블루", "blue irises"), ("그레이", "grey irises"),
])
BROW_THICK = _o([("얇음", "thin"), ("보통", "medium-thickness"), ("두꺼움", "thick")])
BROW_SHAPE = _o([
    ("일자", "straight brows"), ("완만한 아치", "softly arched brows"),
    ("뚜렷한 아치", "strongly arched brows"), ("각진형", "angular brows"),
    ("자연형", "natural untouched brows"),
])
BROW_FINISH = _o([
    ("연함", "lightly filled"), ("내추럴", "naturally groomed"),
    ("결 강조", "brushed-up hair-stroke"), ("선명함", "crisply defined"),
    ("진함", "boldly filled"),
])
NOSE_SIZE = _o([("작음", "a small nose"), ("보통", "a medium nose"), ("큼", "a large nose")])
NOSE_SHAPE = _o([
    ("짧은 코", "a short nose"), ("긴 코", "a long nose"),
    ("직선형", "a straight nose bridge"), ("곡선형", "a softly curved nose"),
    ("코끝이 둥근형", "a rounded nose tip"), ("코끝이 뾰족한형", "a pointed nose tip"),
    ("콧대가 낮은형", "a low nose bridge"), ("콧대가 높은형", "a high nose bridge"),
    ("콧볼이 좁은형", "narrow nostrils"), ("콧볼이 넓은형", "wide nostrils"),
])
MOUTH_SIZE = _o([("작음", "a small mouth"), ("보통", "a medium mouth"), ("큼", "a wide mouth")])
LIP_THICK = _o([
    ("얇음", "thin lips"), ("보통", "medium lips"),
    ("도톰함", "full lips"), ("매우 도톰함", "very full lips"),
])
LIP_SHAPE = _o([
    ("윗입술 얇음", "a thinner upper lip"), ("아랫입술 도톰", "a fuller lower lip"),
    ("균형형", "evenly balanced lips"), ("입꼬리 올라감", "upturned mouth corners"),
    ("입꼬리 내려감", "downturned mouth corners"),
    ("큐피드보우 뚜렷", "a sharply defined cupid's bow"),
])
JAWLINE = _o([("부드러움", "a soft jawline"), ("갸름함", "a slim jawline"),
              ("각짐", "a square jawline"), ("뚜렷함", "a strongly defined jawline")])
CHIN = _o([("짧은 턱", "a short chin"), ("보통", "an average chin"),
           ("긴 턱", "a long chin"), ("뾰족한 턱", "a pointed chin"),
           ("넓은 턱", "a wide chin")])
CHEEKBONE = _o([("낮음", "low cheekbones"), ("보통", "average cheekbones"),
                ("도드라짐", "prominent cheekbones"), ("높은 광대", "high cheekbones")])

# ============================================================ 10~14. 헤어
HAIR_COLOR = _o([
    ("제트 블랙", "jet black"), ("블랙", "black"), ("내추럴 블랙", "natural soft black"),
    ("다크 초콜릿 브라운", "dark chocolate brown"), ("다크 브라운", "dark brown"),
    ("내추럴 브라운", "natural brown"), ("초콜릿 브라운", "chocolate brown"),
    ("밀크 브라운", "milk brown"), ("라이트 브라운", "light brown"),
    ("애쉬 블랙", "ash black"), ("애쉬 브라운", "ash brown"),
    ("애쉬 베이지", "ash beige"), ("애쉬 그레이", "ash grey"),
    ("다크 블론드", "dark blonde"), ("허니 블론드", "honey blonde"),
    ("골든 블론드", "golden blonde"), ("베이지 블론드", "beige blonde"),
    ("애쉬 블론드", "ash blonde"), ("플래티넘 블론드", "platinum blonde"),
    ("레드 브라운", "red brown"), ("코퍼", "copper"),
    ("오렌지 코퍼", "orange copper"), ("와인", "wine red"), ("버건디", "burgundy"),
    ("핑크", "pink"), ("블루", "blue"), ("퍼플", "purple"),
    ("그린", "green"), ("실버", "silver"), ("화이트", "white"),
])
DYE_STYLE = _o([
    ("전체 단색", "coloured evenly all over"), ("자연 모발", "undyed natural hair"),
    ("뿌리 어두움", "with darker roots"), ("옴브레", "in an ombre fade"),
    ("발레아쥬", "with soft balayage"), ("하이라이트", "with fine highlights"),
    ("투톤", "in a two-tone colour split"),
])
HAIR_LENGTH = _o([
    ("삭발", "*shaved"), ("매우 짧음", "very short cropped"),
    ("숏컷", "short"), ("귀 아래", "ear-length"),
    ("턱선 단발", "jaw-length"), ("어깨 단발", "shoulder-length"),
    ("쇄골", "collarbone-length"), ("가슴 위", "upper-chest-length"),
    ("가슴", "chest-length"), ("허리", "waist-length"),
])
HAIR_TEXTURE = _o([
    ("완전 직모", "perfectly straight"), ("자연 직모", "naturally straight"),
    ("약한 C컬", "with a soft C-curl at the ends"),
    ("굵은 C컬", "with a strong C-curl at the ends"),
    ("자연 웨이브", "naturally wavy"), ("굵은 웨이브", "in loose thick waves"),
    ("잔 웨이브", "in fine crimped waves"), ("약한 곱슬", "lightly curly"),
    ("곱슬", "curly"), ("강한 컬", "tightly coiled"),
])
HAIR_THICK = _o([("가늘음", "fine strands"), ("보통", "medium strands"),
                 ("굵음", "thick strands")])
HAIR_VOLUME = _o([("적음", "thin sparse volume"), ("보통", "average volume"),
                  ("풍성함", "abundant volume")])
BANGS = _o([
    ("없음", "no bangs, forehead exposed"), ("풀뱅", "blunt full bangs"),
    ("시스루뱅", "wispy see-through bangs"), ("사이드뱅", "side-swept bangs"),
    ("커튼뱅", "curtain bangs parted in the middle"),
    ("처피뱅", "choppy textured bangs"), ("긴 앞머리", "long front pieces"),
    ("옆으로 넘김", "front hair swept to one side"),
])
HAIR_STYLING = _o([
    ("자연스럽게 풀기", "worn down naturally"), ("깔끔한 스트레이트", "straightened sleek"),
    ("볼륨 스트레이트", "straight with root volume"), ("C컬", "styled in a C-curl"),
    ("S컬", "styled in an S-curl"), ("웨이브", "styled into waves"),
    ("슬릭백", "slicked back"), ("웨트 헤어", "wet-look styled"),
    ("로우 포니테일", "in a low ponytail"), ("하이 포니테일", "in a high ponytail"),
    ("로우 번", "in a low bun"), ("하이 번", "in a high bun"),
    ("반묶음", "half-up half-down"), ("브레이드", "braided"),
    ("헝클어진 내추럴", "tousled and undone"),
    ("댄디컷", "in a tidy dandy cut"), ("가르마", "with a clean side part"),
    ("쉼표머리", "in a comma-shaped fringe style"), ("리젠트", "in a regent pompadour"),
    ("크롭컷", "in a short crop cut"), ("버즈컷", "in a buzz cut"),
    ("포마드", "pomade-styled"), ("장발", "worn long"),
])

# ============================================================ 15~20. 메이크업
MK_LEVEL = _o([
    ("Bare Face", "no makeup at all"), ("No-Makeup Makeup", "invisible no-makeup makeup"),
    ("매우 연함", "very light makeup"), ("내추럴", "natural makeup"),
    ("데일리", "everyday makeup"), ("또렷함", "clearly defined makeup"),
    ("글래머러스", "glamorous makeup"), ("강한 메이크업", "heavy makeup"),
    ("에디토리얼", "editorial statement makeup"),
])
MK_TONE = _o([
    ("뉴트럴", "neutral"), ("웜 베이지", "warm beige"), ("피치", "peach"),
    ("코랄", "coral"), ("오렌지", "orange"), ("골드", "gold"),
    ("쿨 핑크", "cool pink"), ("로지", "rosy"), ("모브", "mauve"),
    ("브라운", "brown"), ("레드", "red"), ("그레이·쿨", "cool grey"),
    ("모노크롬", "monochrome"),
])
MK_BASE = _o([
    ("거의 없음", "almost no base"), ("투명 피부", "a sheer translucent base"),
    ("내추럴", "a natural base"), ("글로우", "a glowing base"),
    ("물광", "a dewy base"), ("새틴", "a satin base"),
    ("세미매트", "a semi-matte base"), ("매트", "a matte base"),
    ("풀커버", "a full-coverage base"),
])
MK_EYE = _o([
    ("거의 없음", "almost no eye makeup"), ("음영만", "soft shading only"),
    ("내추럴", "natural eye makeup"), ("속눈썹 강조", "emphasised lashes"),
    ("아이라인 강조", "a defined eyeliner"), ("눈꼬리 강조", "an extended outer corner"),
    ("브라운 스모키", "a brown smoky eye"), ("블랙 스모키", "a black smoky eye"),
    ("글리터", "glittered lids"), ("컬러 아이", "coloured eyeshadow"),
    ("그래픽 아이라인", "a graphic liner"),
])
LIP_COLOR = _o([
    ("누드 베이지", "nude beige"), ("누드 핑크", "nude pink"), ("피치", "peach"),
    ("코랄", "coral"), ("핑크", "pink"), ("로즈", "rose"), ("모브", "mauve"),
    ("브릭", "brick"), ("오렌지 레드", "orange red"), ("클래식 레드", "classic red"),
    ("버건디", "burgundy"), ("브라운", "brown"),
])
LIP_FINISH = _o([
    ("거의 없음", "bare"), ("립밤", "balmy"), ("틴트", "tinted"),
    ("그라데이션", "gradient"), ("풀립", "fully filled in"),
    ("글로시", "glossy"), ("새틴", "satin"), ("매트", "matte"),
])
BEARD = _o([
    ("없음", "no facial hair"), ("면도 직후", "freshly shaved"),
    ("옅은 스터블", "light stubble"), ("진한 스터블", "heavy stubble"),
    ("콧수염", "a moustache"), ("턱수염", "a chin beard"),
    ("짧은 풀비어드", "a short full beard"), ("긴 풀비어드", "a long full beard"),
])

# ============================================================ 21. 얼굴 특징 (다중)
FEATURES = {
    "주근깨": "freckles across the nose",
    "볼 주근깨": "freckles on the cheeks",
    "점": "a small mole on the face",
    "눈 밑 점": "a mole under one eye",
    "보조개": "dimples when smiling",
    "홍조": "a natural blush on the cheeks",
    "다크서클": "faint dark circles",
    "애교살": "soft under-eye aegyo-sal",
    "치아 노출 미소": "a smile showing the teeth",
    "덧니": "one slightly overlapping tooth",
    "갭투스": "a small gap between the front teeth",
    "얼굴 흉터": "a small scar on the face",
    "피어싱": "small ear piercings",
    "타투": "a small visible tattoo",
    "안경": "wearing clear-framed glasses",
}

# ============================================================ 22~25. 무드
IMPRESSION = _o([(k, v) for k, v in [
    ("귀여운", "cute"), ("사랑스러운", "endearing"), ("순한", "gentle"),
    ("친근한", "approachable"), ("밝은", "bright"), ("발랄한", "bubbly"),
    ("청순한", "innocent"), ("내추럴한", "unaffected"), ("차분한", "calm"),
    ("단정한", "neat"), ("지적인", "intelligent"), ("신뢰감 있는", "trustworthy"),
    ("성숙한", "mature"), ("우아한", "elegant"), ("세련된", "refined"),
    ("도시적인", "urban"), ("시크한", "chic"), ("쿨한", "cool"),
    ("힙한", "hip"), ("강렬한", "intense"), ("카리스마 있는", "charismatic"),
    ("고급스러운", "luxurious"), ("관능적인", "sensual"), ("중성적인", "androgynous"),
]])
EXPRESSION = _o([
    ("무표정", "a neutral expression"), ("편안한 표정", "a relaxed expression"),
    ("옅은 미소", "a faint smile"), ("자연스러운 미소", "a natural smile"),
    ("활짝 웃음", "a wide smile"), ("치아 보이는 웃음", "a smile showing teeth"),
    ("장난스러운 표정", "a playful expression"), ("자신감 있는 표정", "a confident expression"),
    ("진지함", "a serious expression"), ("차가운 표정", "a cool detached expression"),
    ("강렬한 눈빛", "an intense gaze"), ("놀람", "a surprised look"),
    ("호기심", "a curious look"), ("행복", "a happy look"),
])
FASHION = _o([
    ("베이직", "basic"), ("데일리 캐주얼", "everyday casual"), ("캠퍼스", "campus"),
    ("미니멀", "minimal"), ("스트리트", "street"), ("Y2K", "Y2K"),
    ("스포티", "sporty"), ("애슬레저", "athleisure"), ("러블리", "lovely"),
    ("페미닌", "feminine"), ("클래식", "classic"), ("프레피", "preppy"),
    ("댄디", "dandy"), ("비즈니스 캐주얼", "business casual"), ("포멀", "formal"),
    ("오피스", "office"), ("모던", "modern"), ("시크", "chic"),
    ("하이패션", "high-fashion"), ("럭셔리", "luxury"), ("빈티지", "vintage"),
    ("워크웨어", "workwear"), ("아웃도어", "outdoor"),
])
PERSONA = _o([
    ("대학생", "a university student"), ("취업준비생", "a job seeker"),
    ("신입사원", "a junior employee"), ("직장인", "an office worker"),
    ("전문직", "a professional"), ("관리자", "a manager"),
    ("CEO·임원", "a company executive"), ("크리에이터", "a creator"),
    ("인플루언서", "an influencer"), ("아티스트", "an artist"),
    ("운동선수", "an athlete"), ("트레이너", "a personal trainer"),
    ("부모", "a parent"), ("주양육자", "a primary caregiver"),
    ("소상공인", "a small business owner"), ("시니어", "a senior"),
])

# ============================================================ 축 정의
def A(key, label, table, **kw):
    d = {"key": key, "label": label, "table": table, "type": "select"}
    d.update(kw)
    return d


GROUPS = [
    ("MODEL · 기본", [
        A("sex", "성별 표현", SEX, default="여성", required=True),
        A("age", "보이는 연령", AGE, default="20대 후반"),
        A("region", "지역적 외형", REGION, default="한국계"),
        A("persona", "역할·페르소나", PERSONA),
    ]),
    ("BODY · 키·체형", [
        A("height", "키", HEIGHT),
        A("height_cm", "키 직접 입력(cm)", None, type="text", ph="예: 167"),
        A("body", "체형", BODY),
        A("muscle", "근육량", MUSCLE),
        A("shoulder", "어깨", SHOULDER),
        A("proportion", "상·하체 비율", PROPORTION),
        A("limbs", "팔다리", LIMBS),
    ]),
    ("SKIN · 피부", [
        A("skin", "피부색", SKIN),
        A("undertone", "언더톤", UNDERTONE),
        A("skin_texture", "피부 질감", SKIN_TEXTURE),
        A("skin_finish", "피부 표현", SKIN_FINISH),
    ]),
    ("FACE · 얼굴", [
        A("face", "얼굴형", FACE),
        A("jawline", "턱선", JAWLINE),
        A("chin", "턱 형태", CHIN),
        A("cheekbone", "광대", CHEEKBONE),
        A("nose_size", "코 크기", NOSE_SIZE),
        A("nose_shape", "코 형태", NOSE_SHAPE),
        A("mouth_size", "입 크기", MOUTH_SIZE),
        A("lip_thick", "입술 두께", LIP_THICK),
        A("lip_shape", "입 형태", LIP_SHAPE),
    ]),
    ("EYES · 눈·눈썹", [
        A("eye_size", "눈 크기", EYE_SIZE),
        A("eye_shape", "눈 형태", EYE_SHAPE),
        A("eyelid", "쌍꺼풀", EYELID),
        A("iris", "눈동자 색", IRIS),
        A("brow_thick", "눈썹 굵기", BROW_THICK),
        A("brow_shape", "눈썹 형태", BROW_SHAPE),
        A("brow_finish", "눈썹 표현", BROW_FINISH),
    ]),
    ("HAIR · 머리", [
        A("hair_color", "머리색", HAIR_COLOR),
        A("dye", "염색 방식", DYE_STYLE),
        A("hair_length", "길이", HAIR_LENGTH),
        A("hair_texture", "질감", HAIR_TEXTURE),
        A("hair_thick", "모발 굵기", HAIR_THICK),
        A("hair_volume", "모발 양", HAIR_VOLUME),
        A("bangs", "앞머리", BANGS),
        A("hair_styling", "스타일링", HAIR_STYLING),
    ]),
    ("MAKEUP · 메이크업", [
        A("mk_level", "강도", MK_LEVEL),
        A("mk_tone", "전체 톤", MK_TONE),
        A("mk_base", "베이스", MK_BASE),
        A("mk_eye", "아이", MK_EYE),
        A("lip_color", "립 색상", LIP_COLOR),
        A("lip_finish", "립 표현", LIP_FINISH),
        A("beard", "수염", BEARD),
    ]),
    ("DETAIL · 얼굴 특징", [
        A("features", "특징 (여러 개 선택)", FEATURES, type="multi"),
    ]),
    ("MOOD · 인상·분위기", [
        A("impression", "전체 인상", IMPRESSION),
        A("impression2", "인상 (보조)", IMPRESSION),
        A("expression", "표정", EXPRESSION),
        A("fashion", "패션 스타일", FASHION),
    ]),
]
AXES = [a for _t, axes in GROUPS for a in axes]
BY_KEY = {a["key"]: a for a in AXES}
DEFAULTS = {a["key"]: a.get("default", NONE) for a in AXES if a["type"] == "select"}


# ============================================================ 조립
CHILD_NOUN = {"여성": "girl", "남성": "boy", "중성적": "child"}
CHILD_SAFE = ("This is a children's clothing catalogue shot. The child is fully clothed in the "
              "product, standing naturally in a plain studio, with a relaxed age-appropriate "
              "posture and expression. No makeup, no adult styling, no tight close-up of the face "
              "filling the frame, nothing suggestive - the clothing is the subject.")


def is_child(sel):
    ax = BY_KEY.get("age")
    return (ax["table"].get((sel or {}).get("age") or "", "") or "").startswith("*")


def _v(sel, key):
    """고른 값의 영어 조각. 안 골랐으면 ''."""
    ax = BY_KEY.get(key)
    if not ax or ax["type"] != "select":
        return ""
    return (ax["table"] or {}).get(sel.get(key) or "", "")


def _join(items, sep=", "):
    return sep.join([i for i in items if i])


def compose(sel):
    sel = dict(sel or {})
    sex_key = sel.get("sex") if sel.get("sex") in SEX else "여성"
    s = SEX[sex_key]
    out = []

    # --- 정체성
    child = is_child(sel)
    age = _v(sel, "age")
    ident = ["a"]
    region = _v(sel, "region")
    if region:
        ident.append(region)
    if child:
        ident.append(CHILD_NOUN.get(sex_key, "child"))
        ident.append("child model")
        line = " ".join(ident) + ", " + age[1:]
    else:
        ident.append(s["noun"])
        ident.append("fashion model")
        line = " ".join(ident)
        if age:
            line += " who " + age
        persona = _v(sel, "persona")
        if persona:
            line += ", presenting as " + persona
    out.append(line)

    # --- 체형
    cm = str(sel.get("height_cm") or "").strip()
    cm = re.sub(r"[^0-9]", "", cm)[:3]
    stature = ("about %scm tall" % cm) if cm else _v(sel, "height")
    has_bits = [_v(sel, k) for k in ("body", "muscle", "shoulder", "proportion", "limbs")]
    has_bits = [b for b in has_bits if b]
    if stature and has_bits:
        out.append("%s is %s and has %s" % (s["sub"], stature, _join(has_bits)))
    elif stature:
        out.append("%s is %s" % (s["sub"], stature))
    elif has_bits:
        out.append("%s has %s" % (s["sub"], _join(has_bits)))

    # --- 피부
    skin_bits = [_v(sel, k) for k in ("skin", "undertone", "skin_texture", "skin_finish")]
    skin_bits = [b for b in skin_bits if b]
    if skin_bits:
        out.append("Skin: " + _join(skin_bits))

    # --- 얼굴
    face_bits = [_v(sel, k) for k in
                 ("face", "jawline", "chin", "cheekbone",
                  "nose_size", "nose_shape", "mouth_size", "lip_thick", "lip_shape")]
    face_bits = [b for b in face_bits if b]
    if face_bits:
        out.append("Face: " + _join(face_bits))

    # --- 눈·눈썹
    size, shape = _v(sel, "eye_size"), _v(sel, "eye_shape")
    eye_bits = []
    if shape.startswith("~"):
        eye_bits.append(_join([size, "eyes"], " ") + " " + shape[1:])
    elif size or shape:
        eye_bits.append(_join([size, shape, "eyes"], " "))
    eye_bits += [_v(sel, "eyelid"), _v(sel, "iris")]
    eye_bits = [b for b in eye_bits if b]
    brow = _join([_v(sel, "brow_thick"), _v(sel, "brow_shape")], " ")
    if brow:
        brow = brow if "brow" in brow else brow + " brows"
        fin = _v(sel, "brow_finish")
        if fin:
            brow += ", " + fin
        eye_bits.append(brow)
    elif _v(sel, "brow_finish"):
        eye_bits.append(_v(sel, "brow_finish") + " brows")
    if eye_bits:
        out.append("Eyes: " + _join(eye_bits))

    # --- 머리
    length, colour, dye = _v(sel, "hair_length"), _v(sel, "hair_color"), _v(sel, "dye")
    hair_bits = []
    if length == "*shaved":
        hair_bits.append(_join(["a shaved head", colour and ("in " + colour)], ", "))
    elif length or colour or dye:
        head = _join([length, colour, "hair"], " ")
        if dye:
            head += " " + dye
        hair_bits.append(head)
    for k in ("hair_texture", "hair_thick", "hair_volume", "bangs", "hair_styling"):
        hair_bits.append(_v(sel, k))
    hair_bits = [b for b in hair_bits if b]
    if hair_bits:
        out.append("Hair: " + _join(hair_bits))

    # --- 메이크업 / 수염 (아동은 건너뛴다)
    mk_bits = []
    if child:
        mk_bits = None
    lvl, tone = ("", "") if child else (_v(sel, "mk_level"), _v(sel, "mk_tone"))
    if lvl:
        mk_bits.append(lvl + ((" in %s tones" % tone) if tone else ""))
    elif tone:
        mk_bits.append("makeup in %s tones" % tone)
    if not child:
        mk_bits.append(_v(sel, "mk_base"))
        mk_bits.append(_v(sel, "mk_eye"))
        lipc, lipf = _v(sel, "lip_color"), _v(sel, "lip_finish")
        if lipc or lipf:
            mk_bits.append(_join([lipf, lipc], " ") + " lips")
    if mk_bits is not None:
        mk_bits = [b for b in mk_bits if b]
        if mk_bits:
            out.append("Makeup: " + _join(mk_bits))
        if _v(sel, "beard"):
            out.append("Facial hair: " + _v(sel, "beard"))

    # --- 특징
    feats = sel.get("features") or []
    if isinstance(feats, str):
        feats = [feats]
    fe = [FEATURES[f] for f in feats if f in FEATURES]
    if fe:
        out.append("Distinguishing features: " + _join(fe))

    # --- 무드
    imp = _join([_v(sel, "impression"), _v(sel, "impression2")], " and ")
    mood_bits = []
    if imp:
        mood_bits.append("reads as %s" % imp)
    if _v(sel, "expression"):
        mood_bits.append("wearing %s" % _v(sel, "expression"))
    if mood_bits:
        out.append("%s %s" % (s["sub"], _join(mood_bits, ", ")))
    if _v(sel, "fashion"):
        out.append("Hair, makeup and styling follow a %s mood; "
                   "the garment itself stays exactly as the reference product"
                   % _v(sel, "fashion"))

    text = ". ".join([o.strip().rstrip(".") for o in out if o.strip()]) + "."
    if child:
        text += " " + CHILD_SAFE
    return text


# ============================================================ 화면용 / 문자열 해석
def traits_json():
    groups = []
    for title, axes in GROUPS:
        items = []
        for a in axes:
            it = {"key": a["key"], "label": a["label"], "type": a["type"],
                  "default": a.get("default", NONE)}
            if a["type"] == "text":
                it["ph"] = a.get("ph", "")
            else:
                it["options"] = list(a["table"].keys())
            items.append(it)
        groups.append({"title": title, "items": items})
    return groups


def axis_options(key):
    a = BY_KEY.get(key)
    return list(a["table"].keys()) if a and a["type"] == "select" else []


_LOOKUP = {}
for _a in AXES:
    if _a["type"] == "select" and _a["key"] != "sex":
        for _k in _a["table"]:
            if _k != NONE:
                _LOOKUP.setdefault(_k, _a["key"])


def parse_spec(text):
    """'여성/20대 초반/슬림/밝음/계란형' → 선택 dict. 못 알아들으면 None."""
    toks = [t.strip() for t in re.split(r"[/,·|]+", str(text or "")) if t.strip()]
    if not toks:
        return None
    sel, hit = {}, 0
    for t in toks:
        if t in SEX:
            sel["sex"] = t; hit += 1; continue
        if t in FEATURES:
            sel.setdefault("features", []).append(t); hit += 1; continue
        k = _LOOKUP.get(t)
        if k and k not in sel:
            sel[k] = t; hit += 1
    return sel if hit >= 2 else None


def describe(who):
    """dict / 스펙 문자열 / 영어 직접 묘사 → 영어 인물 묘사."""
    if isinstance(who, dict):
        return compose(who)
    text = str(who or "").strip()
    if not text:
        return compose({"sex": "여성", "age": "20대 후반", "region": "한국계"})
    sel = parse_spec(text)
    return compose(sel) if sel else text
