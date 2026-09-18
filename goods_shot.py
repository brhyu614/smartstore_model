#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스마트스토어 상세페이지 이미지 생성기 (단독 실행)
=================================================
옷 사진 폴더를 넣으면 상품마다 6컷을 만들어 저장합니다.
Dify 도, 내 서버도 필요 없습니다. 파이썬 표준 라이브러리만 씁니다.

  ① 대표컷      2:3   모델이 옷을 입은 메인 컷 (좌상단 카피 여백 확보)
  ② 정면 착용   2:3   전신 정면
  ③ 측면 착용   2:3   45도 측면
  ④ 상반신      2:3   목선·어깨·원단 클로즈업
  ⑤ 원단 디테일 1:1   제품만, 매크로
  ⑥ 등록 썸네일 1:1   제품만, 검색 리스트용

인물 고정
---------
①을 먼저 만들고, ②③④는 **①의 이미지를 참조로 함께 보냅니다.**
그래서 컷마다 같은 사람, 같은 옷이 나옵니다.

준비
----
    OpenRouter 키만 있으면 됩니다.  https://openrouter.ai/keys
    export OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx

    (선택) 결과를 웹 주소로도 갖고 싶으면
    export IMGBB_API_KEY=xxxxxxxx        # https://api.imgbb.com

폴더 준비
---------
    옷사진/
      shirt01.jpg
      dress02.png
      products.csv        ← 없으면 파일명을 제품명으로 씁니다

    products.csv (엑셀에서 UTF-8 CSV로 저장)
        파일,제품명,모델
        shirt01.jpg,아이보리 골지 크롭 니트,20대 후반 내추럴
        dress02.png,베이지 오버핏 니트 원피스,

    모델 칸에는 항목을 / 로 이어 적습니다 (순서 무관, 빠진 건 기본값)
        여성/20대 초반/아담/둥근형/긴 웨이브/귀여운/청순 물광/웜톤/캠퍼스룩
        남성/30대 초반/넓은 어깨/각진형/가르마/지적인/옅은 수염/쿨톤/비즈니스 캐주얼
        고를 수 있는 항목 전체:  python3 goods_shot.py --list-models
        성별 지역 연령 체형 피부색 인상 얼굴형 쌍꺼풀 헤어 머리색 앞머리 메이크업 톤 패션무드
        · 영어 직접 묘사도 가능

실행
----
    python3 goods_shot.py ./옷사진 --dry-run       # 계획만 보기
    python3 goods_shot.py ./옷사진 --limit 1       # 한 건만 (요금 확인)
    python3 goods_shot.py ./옷사진                 # 전체
    python3 goods_shot.py ./옷사진 --imgbb         # imgbb 업로드까지
    python3 goods_shot.py ./옷사진 --only hero --force               # 대표컷만 다시
    python3 goods_shot.py ./옷사진 --only hero --force --who "여성/20대 초반/아담/귀여운"  # 다른 인물로
    python3 goods_shot.py ./옷사진 --only wear side close --force     # 인물 바꾼 뒤 나머지 맞추기
    python3 goods_shot.py ./옷사진 --size 2K       # 고해상도
    python3 goods_shot.py ./옷사진 --who "@우리쇼핑몰 기본모델"   # 저장해 둔 모델 쓰기
    python3 goods_shot.py --list-saved             # 저장된 모델 목록

결과
----
    옷사진/out/<제품명>/hero.png … thumb.png
    옷사진/results.csv                 상품별 경로(+imgbb 주소)
    이미 만든 컷은 건너뜁니다. 중간에 끊겨도 다시 실행하면 이어갑니다.
"""

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OR_URL = "https://openrouter.ai/api/v1/images"
IMGBB_URL = "https://api.imgbb.com/1/upload"
OR_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
IMGBB_KEY = (os.environ.get("IMGBB_API_KEY") or "").strip()

CUTS = ["hero", "wear", "side", "close", "detail", "thumb"]
ASPECT = {"hero": "2:3", "wear": "2:3", "side": "2:3", "close": "2:3",
          "detail": "1:1", "thumb": "1:1"}
LABEL = {"hero": "① 대표컷", "wear": "② 정면 착용", "side": "③ 측면 착용",
         "close": "④ 상반신", "detail": "⑤ 원단 디테일", "thumb": "⑥ 썸네일"}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

PRESETS = {
    # ---------------- 여성
    "20대 초반 슬림": "a Korean female fashion model in her early 20s, about 170cm tall with a slim willowy build, small oval face, long straight dark-brown hair parted in the middle and falling past the shoulders, clean dewy skin with light no-makeup makeup, calm neutral expression",
    "20대 초반 캠퍼스 발랄": "a Korean female fashion model in her early 20s, about 163cm tall with a petite slender build, round youthful face with soft cheeks, shoulder-length layered black hair with light bangs, fresh glowy skin and pink-toned lip tint, bright cheerful expression with a light smile",
    "20대 중반 청순": "a Korean female fashion model in her mid 20s, about 167cm tall with a slim balanced build, clean egg-shaped face with double eyelids, long straight black hair tucked behind both ears, translucent porcelain skin with soft rosy makeup, serene gentle expression",
    "20대 후반 내추럴": "a Korean female fashion model in her late 20s, about 166cm tall with a natural healthy build, soft round-oval face, shoulder-length wavy dark hair tucked behind one ear, warm natural makeup with soft coral lips, gentle relaxed smile",
    "20대 후반 시크 도시": "a Korean female fashion model in her late 20s, about 172cm tall with a lean angular build, sharp defined cheekbones and straight brows, sleek jet-black hair pulled into a low tight ponytail, matte neutral makeup with a nude lip, cool composed expression",
    "30대 초반 커리어": "a Korean female fashion model in her early 30s, about 165cm tall with an average balanced build, defined jawline, glossy black chin-length bob with a clean side part, polished natural makeup, composed confident expression",
    "30대 중반 미니멀": "a Korean female fashion model in her mid 30s, about 168cm tall with a slim toned build, calm refined features, dark brown hair in a smooth shoulder-length cut swept behind the ears, understated matte makeup, quiet self-assured expression",
    "40대 우아": "a Korean female fashion model in her mid 40s, about 164cm tall with an elegant slender build, refined features with light natural expression lines, dark brown hair in a low tidy chignon, sophisticated soft makeup, warm dignified expression",
    "50대 품격": "a Korean female fashion model in her early 50s, about 162cm tall with a graceful upright posture and softly rounded build, gentle mature features with natural fine lines, elegant short salt-and-pepper bob, refined light makeup, serene confident expression",
    "여성 글래머러스": "a Korean female fashion model in her late 20s, about 168cm tall with a curvy hourglass figure, full bust and defined waist, oval face with full lips, long loose chocolate-brown waves, warm glossy makeup, poised confident expression",
    "여성 통통 루즈핏": "a Korean plus-size female fashion model in her late 20s, about 165cm tall with a soft full-figured body and rounded shoulders, friendly round face with full cheeks, shoulder-length wavy brown hair, fresh natural makeup, warm approachable smile",
    "여성 아담 키작은": "a Korean female fashion model in her mid 20s, about 156cm tall with a petite compact build and short proportions, small round face, neat medium-length dark hair, clean natural makeup, bright friendly expression",
    "여성 장신 하이패션": "a Korean female fashion model in her mid 20s, about 176cm tall with very long legs and a striking runway build, angular sculpted face with high cheekbones, slicked-back dark hair, editorial bold-brow makeup, intense unsmiling expression",
    "여성 스포티": "a Korean female fashion model in her mid 20s, about 169cm tall with an athletic toned build and defined shoulders, healthy tanned skin, high ponytail with dark hair, minimal fresh makeup, energetic confident expression",

    # ---------------- 남성
    "20대 남성": "a Korean male fashion model in his mid 20s, about 183cm tall with a lean athletic build, sharp clean jawline, short black hair styled up off the forehead, clear skin, calm confident expression",
    "20대 남성 캐주얼": "a Korean male fashion model in his early 20s, about 178cm tall with a slim boyish build, soft youthful face, slightly tousled dark brown hair with a natural fringe, clear fresh skin, relaxed easy smile",
    "30대 남성 댄디": "a Korean male fashion model in his early 30s, about 181cm tall with a lean well-proportioned build, refined features and a defined jaw, neatly combed black hair with a clean side part, groomed light stubble, composed sophisticated expression",
    "40대 남성 중후": "a Korean male fashion model in his early 40s, about 179cm tall with a solid steady build, mature features with light expression lines, short dark hair greying lightly at the temples, calm dignified expression",
    "남성 근육질": "a Korean male fashion model in his late 20s, about 185cm tall with a broad muscular build, wide shoulders and a defined chest, strong square jaw, short cropped black hair, healthy tanned skin, powerful confident expression",
    "남성 넉넉한 체형": "a Korean male fashion model in his early 30s, about 176cm tall with a comfortably heavier build and rounded midsection, friendly broad face, short neat black hair, warm approachable smile",

    # ---------------- 해외
    "서구권 여성 20대": "a Caucasian female fashion model in her mid 20s, about 175cm tall with a slim long-limbed build, oval face with light freckles across the nose, long wavy light-brown hair, natural minimal makeup, relaxed confident expression",
    "서구권 남성 30대": "a Caucasian male fashion model in his early 30s, about 186cm tall with a lean athletic build, angular jaw with short groomed beard, medium-length dark blond hair swept back, calm assured expression",
}

# 화면에서 묶어 보여줄 순서
PRESET_GROUPS = [
    ("여성", ["20대 초반 슬림", "20대 초반 캠퍼스 발랄", "20대 중반 청순",
             "20대 후반 내추럴", "20대 후반 시크 도시", "30대 초반 커리어",
             "30대 중반 미니멀", "40대 우아", "50대 품격"]),
    ("여성 · 체형", ["여성 글래머러스", "여성 통통 루즈핏", "여성 아담 키작은",
                  "여성 장신 하이패션", "여성 스포티"]),
    ("남성", ["20대 남성", "20대 남성 캐주얼", "30대 남성 댄디", "40대 남성 중후",
             "남성 근육질", "남성 넉넉한 체형"]),
    ("해외", ["서구권 여성 20대", "서구권 남성 30대"]),
]
DEFAULT_PRESET = "20대 후반 내추럴"



# ================================================================ 컷별 포즈 선택지
# 대표컷을 확정한 뒤, 나머지 컷을 어떤 포즈로 뽑을지 고를 수 있다.
_FRONT = ("Full-body front-facing product shot, vertical 2:3 composition. The entire outfit is visible "
          "from head to toe with a small margin above the head and below the feet. Natural fabric drape "
          "and true fit. Shot on an 85mm lens at f/5.6. ")
_SIDE = ("Full-body shot, vertical 2:3 composition, showing the side and back construction of the "
         "product clearly. Shot on an 85mm lens at f/5.6. ")
_UPPER = ("Upper-body crop, vertical 2:3 composition, so the neckline, collar, shoulder seam and upper "
          "fabric texture of the product read clearly. Shot on a 105mm lens at f/2.8 with a shallow "
          "depth of field. ")
_MACRO = ("Extreme macro close-up, square 1:1 composition. Shot on a 90mm macro lens at f/8 so the "
          "whole surface stays sharp. ")
_THUMB = ("Square 1:1 catalog thumbnail, centred and filling most of the frame with even margins, "
          "bright and high contrast so it stands out in a search-result grid, crisp even lighting. ")

POSES = {
 "wear": {
  "정면 기본": _FRONT + "The model stands straight and centred, feet slightly apart, arms relaxed at the sides, facing the camera.",
  "한 손 주머니": _FRONT + "The model stands with weight on one leg, one hand slipped into a pocket, the other arm relaxed, facing the camera.",
  "가볍게 걷는": _FRONT + "The model is caught mid-stride walking toward the camera, one foot forward, arms swinging naturally, fabric moving with the step.",
  "팔짱": _FRONT + "The model stands squared to the camera with arms lightly folded across the chest, shoulders relaxed.",
  "한 발 앞으로": _FRONT + "The model stands in a relaxed contrapposto, one foot placed forward and hips slightly angled, arms loose at the sides.",
 },
 "side": {
  "45도 측면": _SIDE + "The model is turned 45 degrees to one side with the weight on the back foot, one hand resting lightly at the hip, head turned back toward the camera.",
  "완전 측면": _SIDE + "The model stands in full profile at 90 degrees to the camera, arms relaxed, looking straight ahead, so the side seam and silhouette are fully readable.",
  "뒷모습": _SIDE + "The model stands with the back to the camera, arms relaxed at the sides, head facing forward, so the entire back of the product is visible.",
  "돌아보는": _SIDE + "The model is walking away from the camera and turns the head back over one shoulder, so both the back of the product and part of the face are visible.",
 },
 "close": {
  "옷깃 잡기": _UPPER + "The model is cropped from mid-chest to just above the head and pushed to the left of frame, turned about 30 degrees away, chin lowered, eyes off-camera, one hand raised to lightly touch the collar or neckline.",
  "정면 상반신": _UPPER + "The model is cropped from the waist up, squared to the camera, hands relaxed at the sides, looking straight into the lens with a soft expression.",
  "고개 숙임": _UPPER + "The model is cropped from the chest up with the chin lowered and eyes looking down, so attention falls on the neckline and shoulder line of the product.",
  "옆모습 상반신": _UPPER + "The model is cropped from the chest up in profile, showing the shoulder line, sleeve head and side neckline of the product.",
 },
 "detail": {
  "평면 매크로": _MACRO + "The product's material surface, weave and stitching, laid flat and lit with soft raking light that reveals the texture depth. Product only, no model, no hands.",
  "손으로 원단 잡기": _MACRO + "A hand lightly pinches and lifts the fabric so its thickness, drape and weave are visible. Only the hand and the fabric are in frame.",
  "접힌 상태": _MACRO + "The product neatly folded in a small stack, photographed from a low angle so the folded edges, thickness and texture read clearly.",
  "봉제선 클로즈업": _MACRO + "A tight crop on a seam, hem or trim of the product, showing stitch density, thread colour and finishing quality. Product only.",
 },
 "thumb": {
  "플랫레이": _THUMB + "The product only, no model, laid flat and photographed straight from above on a clean light-gray surface.",
  "행거": _THUMB + "The product only, hung on a simple wooden hanger against a clean light-gray wall, falling naturally.",
  "마네킹": _THUMB + "The product only, fitted on a plain faceless mannequin form so the shape and fit read clearly.",
  "모델 전신 축소": _THUMB + "The same model wearing the product, full body centred small in the square frame with generous even margins around them.",
 },
}
POSE_LABEL = {"wear": "② 정면 착용", "side": "③ 측면 착용", "close": "④ 상반신",
              "detail": "⑤ 원단 디테일", "thumb": "⑥ 썸네일"}


def pose_traits_json():
    return pt.traits_json()


def styling_traits_json():
    return sy.traits_json()


def guess_kind(name):
    return sy.guess_kind(name)


def poses_json():
    return [{"cut": c, "label": POSE_LABEL[c], "options": list(POSES[c])}
            for c in ["wear", "side", "close", "detail", "thumb"]]


# ================================================================ 모델 저장함
# 잘 나온 인물 조합을 이름 붙여 저장해 두고 다시 쓴다.
# 파일은 이 스크립트 옆에 생기므로 폴더째 옮겨도 따라간다.
_HERE = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(_HERE, "saved_models.json")
STORE_THUMBS = os.path.join(_HERE, "saved_models")


def load_models():
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_models(d):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def save_model(name, who, thumb=None, look=None):
    """이름으로 저장. thumb 은 대표컷 이미지 바이트(선택), look 은 코디 선택(선택)."""
    name = safe_dir(str(name or "").strip())
    if not name:
        raise ValueError("이름을 적어주세요.")
    d = load_models()
    d[name] = {"who": who, "저장": time.strftime("%Y-%m-%d %H:%M"),
               "묘사": model_desc(who), "코디": look or {}}
    if thumb:
        os.makedirs(STORE_THUMBS, exist_ok=True)
        with open(os.path.join(STORE_THUMBS, name + ".png"), "wb") as f:
            f.write(thumb)
        d[name]["썸네일"] = True
    _write_models(d)
    return name


def delete_model(name):
    d = load_models()
    if name in d:
        d.pop(name)
        _write_models(d)
        try:
            os.remove(os.path.join(STORE_THUMBS, name + ".png"))
        except OSError:
            pass
        return True
    return False


def get_model(name):
    return (load_models().get(name) or {}).get("who")


def get_look(name):
    return (load_models().get(name) or {}).get("코디") or {}


# ================================================================ 인물 조합표
# 축·선택지·문장 조립은 model_traits.py 에 있다 (같은 폴더).
import model_traits as mt                                    # noqa: E402
import pose_traits as pt                                     # noqa: E402
import styling_traits as sy                                  # noqa: E402

AXES = mt.AXES
GROUPS = mt.GROUPS
DEFAULTS = mt.DEFAULTS
traits_json = mt.traits_json
axis_options = mt.axis_options
compose = mt.compose
parse_spec = mt.parse_spec


# --------------------------------------------------------------- 도우미
def clean(s):
    s = str(s or "")
    for ch in ["\\", '"', "\n", "\r", "\t", "{", "}"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())


def model_desc(name):
    """dict / '여성/20대 초반/…' 스펙 / 옛 프리셋 이름 / 영어 직접 묘사 모두 받는다."""
    if isinstance(name, dict):
        return mt.compose(name)
    text = str(name or "").strip()
    if text.startswith("@"):
        saved = get_model(text[1:].strip())
        if saved is not None:
            return mt.compose(saved) if isinstance(saved, dict) else mt.describe(saved)
        raise ValueError("저장된 모델을 찾지 못했습니다: " + text[1:])
    if text in PRESETS:
        return PRESETS[text]
    return mt.describe(text)

ID_LOCK = ("IDENTITY LOCK: every image in this set shows the exact same person. "
           "Keep the identical face shape, eyes, nose, lips, eyebrows, hairstyle, hair colour, "
           "skin tone, height and body proportions in every cut. Never swap the model.")
GARMENT_LOCK = ("GARMENT LOCK: the first reference image is the actual product being sold. "
                "Reproduce it exactly - identical colour and tone, fabric texture and weave, "
                "pattern placement, silhouette, length, neckline, sleeve shape, seams, stitching, "
                "buttons, zippers and trims. Do not redesign, restyle, recolour or simplify it.")
STUDIO_LOCK = ("STUDIO LOCK: clean light-gray seamless studio background (hex EDEDED), "
               "soft diffused commercial lighting from a large softbox at the front-left with a gentle "
               "fill from the right, subtle contact shadow on the floor, neutral white balance at 5500K, "
               "full-frame camera look, photorealistic, ultra-detailed, sharp focus, identical colour "
               "grading across the whole set, high-end Korean e-commerce editorial mood. No extra props.")
# 무지 옷일 때: 글자·로고를 아예 만들지 못하게 막는다
NO_TEXT = "Add no text, no watermark, no logo and no graphic overlay anywhere in the image."
# 프린트·로고가 있는 옷일 때: 원본 그래픽은 살리고, 새로 지어내는 것만 막는다
GRAPHIC_LOCK = (
    "GRAPHIC LOCK: this product carries a printed graphic or logo. Reproduce that artwork exactly as it "
    "appears in the reference images - identical shapes, outlines, line weights, colours, proportions, "
    "spacing and position on the garment. Do not redraw, restyle, simplify, mirror, rescale or re-letter "
    "it. Never invent letters, words, characters or symbols that are not visible in the reference. "
    "Follow the fabric's drape so the print curves and folds naturally with the cloth, keeping its "
    "internal proportions intact. Apart from that existing print, add no text, watermark, logo or "
    "graphic overlay of your own.")
SECOND_REF = ("The second reference image shows the model. "
              "Match that person's face, hair and body exactly.")
# 추가로 올린 옷 사진의 종류 (앞/뒤/옆/디테일 …)
VIEWS = {
    "앞면": "the front of the garment",
    "뒷면": "the back of the garment",
    "옆면": "the side of the garment",
    "안감": "the inside and lining of the garment",
    "디테일": "a close-up of the fabric, stitching and trims",
    "프린트": "a close-up of the printed graphic or logo",
    "부자재": "a close-up of the buttons, zipper or other hardware",
    "펼친컷": "the garment laid flat so its full shape is visible",
    "착용컷": "the garment worn on a body",
    "기타": "another view of the same garment",
}
VIEW_ORDER = list(VIEWS.keys())
_ORD = ["second", "third", "fourth", "fifth", "sixth",
        "seventh", "eighth", "ninth", "tenth"]
EXTRA_TAIL = (
    "Read all of these together as one complete description of a single real garment. "
    "Whenever a cut shows the back, a side, the inside or a close-up, reproduce exactly what "
    "those photos show - the back and the sides are NOT mirrored copies of the front, so never "
    "invent, guess or duplicate a view that is documented in a reference image.")


_VIEW_HINT = [
    ("뒷면", ("back", "rear", "뒤", "뒷")),
    ("앞면", ("front", "앞")),
    ("옆면", ("side", "옆", "측면")),
    ("안감", ("inside", "inner", "lining", "안감", "속")),
    ("프린트", ("print", "logo", "graphic", "프린트", "로고")),
    ("부자재", ("button", "zip", "trim", "단추", "지퍼", "부자재")),
    ("펼친컷", ("flat", "lay", "펼")),
    ("착용컷", ("worn", "wear", "model", "착용")),
    ("디테일", ("detail", "close", "macro", "texture", "디테일", "확대")),
]


def guess_view(path):
    """파일 이름으로 사진 종류를 짐작한다."""
    low = os.path.basename(path).lower()
    for name, keys in _VIEW_HINT:
        if any(k in low for k in keys):
            return name
    return "기타"


def extra_ref_text(views, start):
    """추가 참조 사진 안내문. views 는 한글 라벨 목록, start 는 1부터 센 첫 사진 번호."""
    if not views:
        return ""
    bits = []
    for i, v in enumerate(views):
        n = start + i
        word = ("the %s reference image" % _ORD[n - 2]) if 2 <= n <= 10 \
            else ("reference image %d" % n)
        bits.append("%s shows %s" % (word, VIEWS.get(v) or VIEWS["기타"]))
    return ("ADDITIONAL PRODUCT REFERENCES: " + "; ".join(bits) + ". " + EXTRA_TAIL)

SHOTS = {
 "hero": ("Hero e-commerce detail-page cut, vertical 2:3 composition. The model wears the product, "
          "framed from mid-thigh up and placed off-centre to the right along the golden ratio, with "
          "generous empty negative space in the upper-left third reserved for a copy overlay. Standing "
          "tall and squared to the camera with weight evenly balanced, both arms relaxed at the sides, "
          "chin level, looking straight down the lens with a calm open expression. "
          "Shot on an 85mm lens at f/4."),
 "wear": ("Full-body front-facing product shot, vertical 2:3 composition. The same model stands straight "
          "and centred, feet slightly apart, arms relaxed at the sides, facing the camera, the entire outfit "
          "visible from head to toe with a small margin above the head and below the feet. Natural fabric "
          "drape and true fit. Shot on an 85mm lens at f/5.6."),
 "side": ("Three-quarter angle full-body shot, vertical 2:3 composition. The same model is turned 45 degrees "
          "to one side with the weight on the back foot, one hand resting lightly at the hip, head turned back "
          "toward the camera, so the side seam and back silhouette of the product are clearly readable. "
          "Shot on an 85mm lens at f/5.6."),
 "close": ("Tight upper-body detail crop, vertical 2:3 composition, deliberately different from the hero cut. "
           "The same model is cropped close from mid-chest to just above the head and pushed to the left of frame, "
           "turned about 30 degrees away from the camera with the shoulder nearest the lens dropped and the chin "
           "lowered, eyes looking off-camera to the side rather than at the lens, one hand raised to lightly touch "
           "the collar or neckline so the fabric weight and stitching read clearly. The neckline, shoulder seam and "
           "upper texture of the product fill most of the frame. Shot on a 105mm lens at f/2.8 with a shallow "
           "depth of field, softly blurring the background."),
 "detail": ("Extreme macro close-up, square 1:1 composition, of the product's material surface, weave and stitching, "
            "laid flat and lit with soft raking light that reveals the texture depth. Product only, no model, no hands. "
            "Shot on a 90mm macro lens at f/8 so the whole surface stays sharp."),
 "thumb": ("Square 1:1 catalog thumbnail of the product only, no model, presented flat-lay style, centred and filling "
           "most of the frame with even margins, bright and high contrast so it stands out in a search-result grid, "
           "crisp even lighting. Shot on a 50mm lens at f/8."),
}
# 아동 모델일 때는 얼굴이 화면을 채우는 크롭 대신 옷 위주 크롭을 쓴다
CHILD_CLOSE = ("Upper-body garment detail crop for a children's catalogue, vertical 2:3 composition. "
               "The same child is framed from the waist to just above the shoulders so the neckline, "
               "collar, shoulder seam and fabric texture of the product fill most of the frame; the "
               "face is only partly in frame at the top edge and is not the subject. Natural relaxed "
               "posture, arms at the sides. Shot on an 85mm lens at f/4.")

WITH_MODEL = {"hero": True, "wear": True, "side": True, "close": True,
              "detail": False, "thumb": False}


def build_prompt(cut, product, model, two_refs, graphic=False, extras=0, pose=None,
                 styling=None, kind=None):
    """pose 는 포즈 이름(문자열) 또는 관절 단위 선택(dict) 둘 다 받는다.
    extras 는 추가 사진 개수(정수) 또는 사진 종류 목록(['뒷면','디테일' …]) 둘 다 받는다.
    styling 은 코디 선택 dict, kind 는 제품 종류(상의/하의/원피스 …)."""
    child = "child model" in (model or "")
    shot = SHOTS[cut]
    pose_spec = ""
    if isinstance(pose, dict):
        pose_spec = pt.compose(pose)
    elif pose and cut in POSES and pose in POSES[cut]:
        shot = POSES[cut][pose]
    if child and cut == "close":
        shot = CHILD_CLOSE
    parts = [shot]
    if pose_spec:
        parts.append(pose_spec)
    parts.append("PRODUCT: " + product + ".")
    if WITH_MODEL[cut]:
        parts += ["MODEL: " + model + ".", ID_LOCK]
        # 코디는 모델이 나오는 컷에만 (디테일·썸네일은 제품만 찍는다)
        if styling:
            look = sy.compose(styling, kind)
            if look:
                parts.append(look)
    if two_refs:
        parts.append(SECOND_REF)
    views = (["기타"] * extras) if isinstance(extras, int) else list(extras or [])
    if views:
        parts.append(extra_ref_text(views, 3 if two_refs else 2))
        if "뒷면" in views and cut in ("side", "wear"):
            parts.append("This cut reveals the back of the garment: match the back reference "
                         "photo exactly - its seams, yoke, print, closure and hem.")
    parts.append(GARMENT_LOCK)
    parts.append(GRAPHIC_LOCK if graphic else NO_TEXT)
    parts.append(STUDIO_LOCK)
    return clean(" ".join(parts))


def data_url(blob, mime=None):
    if not mime:
        mime = sniff_mime(blob)
    return "data:%s;base64,%s" % (mime, base64.b64encode(blob).decode())


def sniff_mime(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def ext_for(b):
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(
        sniff_mime(b), ".png")


def safe_dir(s):
    s = re.sub(r'[\\/:*?"<>|]+', "-", str(s or "")).strip()
    return s[:60] or "product"


# --------------------------------------------------------------- API
def post_json(url, payload, headers, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def generate(prompt, refs, aspect, size, model, timeout=420, tries=3):
    """OpenRouter 로 이미지 한 장. refs 는 data URL 또는 http 주소 목록."""
    if not OR_KEY:
        raise RuntimeError("OPENROUTER_API_KEY 가 비어 있습니다.")
    payload = {"model": model, "prompt": prompt, "n": 1,
               "aspect_ratio": aspect, "resolution": size,
               "input_references": [{"type": "image_url", "image_url": {"url": u}}
                                    for u in refs]}
    headers = {"Authorization": "Bearer " + OR_KEY,
               "Content-Type": "application/json"}

    last = ""
    for attempt in range(1, tries + 1):
        try:
            obj = post_json(OR_URL, payload, headers, timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < tries:
                last = "%s %s" % (e.code, body[:120])
                time.sleep(4 * attempt)
                continue
            raise RuntimeError("OpenRouter %s: %s" % (e.code, body))
        except urllib.error.URLError as e:
            if attempt < tries:
                last = str(getattr(e, "reason", e))
                time.sleep(4 * attempt)
                continue
            raise RuntimeError("연결 실패: %s" % (getattr(e, "reason", e),))
        except Exception as e:                      # 연결 끊김·응답 깨짐 등
            if attempt < tries:
                last = "%s: %s" % (type(e).__name__, e)
                time.sleep(4 * attempt)
                continue
            raise RuntimeError("요청 실패: %s: %s" % (type(e).__name__, str(e)[:200]))

        err = obj.get("error")
        if isinstance(err, dict):
            raise RuntimeError("OpenRouter 오류: " + str(err.get("message"))[:300])
        if isinstance(err, str) and err:
            raise RuntimeError("OpenRouter 오류: " + err[:300])
        for item in (obj.get("data") or []):
            if not isinstance(item, dict):
                continue
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"])
            if item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=180) as r:
                    return r.read()
        if attempt < tries:
            last = json.dumps(obj, ensure_ascii=False)[:150]
            time.sleep(3 * attempt)
            continue
        raise RuntimeError("그림이 오지 않았습니다: "
                           + json.dumps(obj, ensure_ascii=False)[:300])
    raise RuntimeError("반복 실패: " + last)


OR_CHAT = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL = os.environ.get("TEXT_MODEL", "google/gemini-3.8-flash")


def chat(system, user, model=None, timeout=120, tries=3):
    """OpenRouter 로 글 한 번. JSON 객체를 돌려준다. 이미지보다 훨씬 싸다."""
    if not OR_KEY:
        raise RuntimeError("OPENROUTER_API_KEY 가 비어 있습니다.")
    payload = {"model": model or TEXT_MODEL,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "temperature": 0.3,
               "response_format": {"type": "json_object"}}
    headers = {"Authorization": "Bearer " + OR_KEY,
               "Content-Type": "application/json"}
    last = ""
    for attempt in range(1, tries + 1):
        try:
            obj = post_json(OR_CHAT, payload, headers, timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < tries:
                last = "%s %s" % (e.code, body[:120]); time.sleep(2 * attempt); continue
            raise RuntimeError("OpenRouter %s: %s" % (e.code, body))
        except Exception as e:
            if attempt < tries:
                last = "%s: %s" % (type(e).__name__, e); time.sleep(2 * attempt); continue
            raise RuntimeError("요청 실패: %s: %s" % (type(e).__name__, str(e)[:200]))
        err = obj.get("error")
        if isinstance(err, dict):
            raise RuntimeError("OpenRouter 오류: " + str(err.get("message"))[:300])
        try:
            txt = obj["choices"][0]["message"]["content"]
        except Exception:
            if attempt < tries:
                last = json.dumps(obj, ensure_ascii=False)[:150]; time.sleep(2); continue
            raise RuntimeError("답이 오지 않았습니다.")
        try:
            return json.loads(txt)
        except Exception:
            m = re.search(r"\{.*\}", txt, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            if attempt < tries:
                last = txt[:150]; time.sleep(1); continue
            raise RuntimeError("답을 읽지 못했습니다: " + txt[:200])
    raise RuntimeError("반복 실패: " + last)


def imgbb_upload(blob, name):
    if not IMGBB_KEY:
        return ""
    body = urllib.parse.urlencode({
        "image": base64.b64encode(blob).decode(), "name": name}).encode()
    req = urllib.request.Request(
        IMGBB_URL + "?key=" + urllib.parse.quote(IMGBB_KEY), data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            obj = json.loads(r.read().decode("utf-8", "replace"))
        d = obj.get("data") or {}
        return d.get("url") or (d.get("image") or {}).get("url") or ""
    except Exception as e:
        print("     imgbb 업로드 실패: %s" % str(e)[:120])
        return ""


# --------------------------------------------------------------- 목록
FIELDS = ["파일", "제품명", "모델", "상태"] + CUTS + ["오류"]


def load_jobs(folder):
    csv_path = os.path.join(folder, "products.csv")
    jobs = []
    if os.path.isfile(csv_path):
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                fn = (row.get("파일") or row.get("file") or "").strip()
                if not fn:
                    continue
                jobs.append({"파일": fn,
                             "제품명": (row.get("제품명") or row.get("product")
                                     or os.path.splitext(fn)[0]).strip(),
                             "모델": (row.get("모델") or row.get("model") or "").strip(),
                             "추가사진": (row.get("추가사진") or "").strip(),
                             "프린트": (row.get("프린트") or "").strip()})
    else:
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith(IMG_EXTS):
                jobs.append({"파일": fn, "제품명": os.path.splitext(fn)[0], "모델": ""})
    return jobs


def save_results(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def existing_cut(outdir, cut):
    for e in (".png", ".jpg", ".webp"):
        p = os.path.join(outdir, cut + e)
        if os.path.isfile(p) and os.path.getsize(p) > 64:
            return p
    return ""


# --------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser(description="상세페이지 6컷 자동 생성")
    ap.add_argument("folder", nargs="?", default=".")
    ap.add_argument("--model", default="google/gemini-3-pro-image",
                    help="이미지 모델 (기본 나노바나나 Pro). 저렴하게: google/gemini-3.1-flash-image")
    ap.add_argument("--size", default="1K", choices=["512", "1K", "2K", "4K"])
    ap.add_argument("--only", nargs="*", choices=CUTS, help="특정 컷만 다시 만들기")
    ap.add_argument("--who", default="",
                    help='이번 실행에만 쓸 인물. 예: "여성/20대 초반/아담/둥근형/긴 웨이브/'
                         '귀여운/캠퍼스룩". 항목은 --list-models 로 확인. 영어 묘사도 가능')
    ap.add_argument("--imgbb", action="store_true", help="imgbb 에도 올려 웹 주소 확보")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="이미 있는 컷도 다시 만들기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-models", action="store_true", help="고를 수 있는 항목 목록 보기")
    ap.add_argument("--list-saved", action="store_true", help="저장해 둔 모델 목록 보기")
    ap.add_argument("--list-poses", action="store_true", help="컷별 포즈 선택지 보기")
    ap.add_argument("--graphic", action="store_true",
                    help="프린트·로고가 있는 옷. 그래픽을 그대로 재현하도록 지시합니다")
    ap.add_argument("--pose", nargs="*", default=[], metavar="컷=포즈",
                    help='컷별 포즈. 예: --pose wear=한 손 주머니 side=뒷모습')
    ap.add_argument("--extra", nargs="*", default=[], metavar="[종류=]경로",
                    help="옷 사진 추가 (앞/뒤/옆/디테일 등, 여러 장). "
                         "예: --extra 뒷면=back.jpg 디테일=cuff.jpg")
    ap.add_argument("--kind", default="", choices=[""] + sy.KIND_ORDER,
                    help="제품 종류. 비우면 제품명으로 짐작합니다")
    ap.add_argument("--wear", nargs="*", default=[], metavar="슬롯=값",
                    help='코디. 예: --wear 하의="검정 슬랙스" 신발="검정 로퍼"')
    ap.add_argument("--no-styling", action="store_true",
                    help="코디를 아예 지정하지 않습니다 (AI가 알아서)")
    ap.add_argument("--list-wear", action="store_true", help="코디 선택지를 보여줍니다")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()

    if args.list_poses:
        print("\n컷별 포즈 선택지  ( --pose 컷=이름 )\n")
        for c in ["wear", "side", "close", "detail", "thumb"]:
            print("  %-8s %-12s %s" % (c, POSE_LABEL[c], " / ".join(POSES[c])))
        print('\n예)  --pose wear=한 발 앞으로 side=뒷모습 thumb=행거')
        return

    if args.list_wear:
        print("\n코디 선택지  ( --wear 슬롯=\"값\" )\n")
        print("제품 종류 (--kind): %s\n" % " / ".join(sy.KIND_ORDER))
        for g in sy.GROUPS:
            print("── %s" % g["title"])
            for k in g["keys"]:
                s = sy.BY_KEY[k]
                print("   %s" % s["key"])
                if s.get("type") == "cascade":
                    for c in s["cats"]:
                        print("      · %-12s %s" % (c["title"], " / ".join(c["options"])))
                    seen = []
                    for c in s["cats"]:            # 값이 같은 축은 한 번만 적는다
                        for a in c["axes"]:
                            sig = (a["key"], tuple(a["options"]))
                            hit = next((x for x in seen if x[0] == sig), None)
                            if hit:
                                hit[1].append(c["title"])
                            else:
                                seen.append((sig, [c["title"]]))
                    for (ak, opts), cats in seen:
                        print("      %s.%s = %s   (%s)"
                              % (s["key"], ak, " / ".join(opts), "·".join(cats)))
                else:
                    for sub in (s.get("optgroups") or [{"title": "", "options": s["options"]}]):
                        head = ("· %s" % sub["title"]) if sub["title"] else "·"
                        print("      %-12s %s" % (head, " / ".join(sub["options"])))
        print('\n예)  --kind 상의 --wear 하의="검정 슬랙스" 신발="검정 로퍼"')
        print("고르지 않은 슬롯은 위 목록의 첫 항목(기본값)이 들어갑니다.")
        return

    if args.list_saved:
        d = load_models()
        if not d:
            print("저장된 모델이 없습니다. 웹 화면에서 [현재 설정 저장] 으로 만들 수 있습니다.")
            return
        print("\n저장된 모델 %d개  ( --who \"@이름\" 으로 사용 )\n" % len(d))
        for k, v in d.items():
            print("  @%s   (%s)" % (k, v.get("저장", "")))
            print("     %s\n" % str(v.get("묘사", ""))[:150])
        return

    if args.list_models:
        print("\n인물은 아래 항목을 조합해 지정합니다. 고르지 않은 항목은 프롬프트에 넣지 않습니다.")
        print('예)  --who "여성/20대 초반/슬림/라이트 베이지/계란형/아몬드형/다크 브라운/시스루뱅/친근한/캠퍼스"\n')
        for title, axes in GROUPS:
            print("── %s" % title)
            for ax in axes:
                if ax["type"] == "text":
                    print("   %-14s (직접 입력)" % ax["label"])
                else:
                    opts = [k for k in ax["table"] if k != mt.NONE]
                    print("   %-14s %s" % (ax["label"], " / ".join(opts)))
            print()
        print("영어로 통째로 묘사해 넘겨도 됩니다.")
        return

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        sys.exit("폴더가 없습니다: " + folder)
    if not OR_KEY and not args.dry_run:
        sys.exit("OPENROUTER_API_KEY 환경변수가 비어 있습니다.\n"
                 "  export OPENROUTER_API_KEY=sk-or-v1-xxxx")
    if args.imgbb and not IMGBB_KEY:
        sys.exit("--imgbb 를 쓰려면 IMGBB_API_KEY 환경변수가 필요합니다.")

    jobs = load_jobs(folder)
    if args.limit:
        jobs = jobs[:args.limit]
    if not jobs:
        sys.exit("처리할 이미지가 없습니다.")
    want = args.only or CUTS
    posemap = {}
    for item in args.pose:
        if "=" in item:
            k, v = item.split("=", 1)
            k, v = k.strip(), v.strip()
            if k in POSES and v in POSES[k]:
                posemap[k] = v
            else:
                sys.exit("포즈를 찾지 못했습니다: %s.  --list-poses 로 확인하세요." % item)

    print("─" * 62)
    print(" 폴더  : %s" % folder)
    print(" 모델  : %s   해상도 %s" % (args.model, args.size))
    print(" 컷    : %s" % " ".join(LABEL[c] for c in want))
    if args.who:
        print(" 모델  : %s" % args.who)
    print(" 상품  : %d건%s%s" % (len(jobs), "  (imgbb 업로드 켜짐)" if args.imgbb else "",
                                "  · 프린트 모드" if args.graphic else ""))
    print("─" * 62)
    for j in jobs:
        print("  · %-26s %s" % (j["파일"], j["제품명"]))
    if args.dry_run:
        print("\n(--dry-run 이라 실제 생성은 하지 않았습니다)")
        return
    print()

    res_path = os.path.join(folder, "results.csv")
    rows, ok_all, fail_all = [], 0, 0

    for i, j in enumerate(jobs, 1):
        src = os.path.join(folder, j["파일"])
        outdir = os.path.join(folder, "out", safe_dir(j["제품명"]))
        row = dict(j, 상태="")
        print("[%d/%d] %s" % (i, len(jobs), j["제품명"]))

        if not os.path.isfile(src):
            print("    ❌ 파일 없음"); row["상태"] = "실패"; row["오류"] = "파일 없음"
            rows.append(row); fail_all += 1; continue

        os.makedirs(outdir, exist_ok=True)
        with open(src, "rb") as f:
            garment = f.read()
        garment_ref = data_url(garment)
        mdesc = model_desc(args.who or j["모델"])

        # 추가 참조 사진 (CLI --extra + products.csv 추가사진 열)
        extra_paths = list(args.extra)
        for nm in [x.strip() for x in (j.get("추가사진") or "").split(";") if x.strip()]:
            v, _, p = nm.rpartition("=")
            p = p if os.path.isabs(p) else os.path.join(folder, p)
            extra_paths.append((v + "=" + p) if v else p)
        extra_refs, extra_views = [], []
        for item in extra_paths:
            v, _, ep = item.rpartition("=")
            v = v.strip()
            if os.path.isfile(ep):
                with open(ep, "rb") as f:
                    extra_refs.append(data_url(f.read()))
                extra_views.append(v if v in VIEWS else guess_view(ep))
                print("    · 추가 사진: %s (%s)" % (os.path.basename(ep), extra_views[-1]))
            else:
                print("    · 추가 사진을 찾지 못했습니다: %s" % ep)
        graphic = args.graphic or (j.get("프린트") or "").upper() in ("Y", "YES", "TRUE", "1", "O", "있음")

        # 코디 (--kind / --wear, 비우면 제품명으로 종류를 짐작하고 기본 코디를 쓴다)
        kind = args.kind or (j.get("종류") or "").strip() or guess_kind(j["제품명"])
        styling = None
        if not args.no_styling:
            styling = {}
            for item in args.wear:
                k, _, v = item.partition("=")
                k, v = k.strip(), v.strip()
                slot = k.split(".")[0]           # "하의" 또는 "하의.핏"
                if slot not in sy.BY_KEY or not v:
                    continue
                styling[k] = [x.strip() for x in v.split(";")] if k == "액세서리" else v
            print("    · 코디: 제품=%s" % kind)
        hero_ref = ""                      # ②③④ 가 쓸 대표컷 참조

        # 이미 만들어 둔 대표컷이 있으면 참조로 재사용
        prev = existing_cut(outdir, "hero")
        if prev and not (args.force and "hero" in want):
            with open(prev, "rb") as f:
                hero_ref = data_url(f.read())

        cut_fail = False
        for cut in CUTS:
            if cut not in want:
                continue
            done = existing_cut(outdir, cut)
            if done and not args.force:
                print("    · %s 건너뜀 (이미 있음)" % LABEL[cut])
                row[cut] = done
                continue
            if cut in ("wear", "side", "close") and not hero_ref:
                print("    · %s 건너뜀 (대표컷이 없어 인물을 고정할 수 없음)" % LABEL[cut])
                continue

            refs = [garment_ref]
            if cut in ("wear", "side", "close"):
                refs.append(hero_ref)
            two = len(refs) == 2
            refs += extra_refs
            prompt = build_prompt(cut, clean(j["제품명"]), mdesc, two,
                                  graphic=graphic, extras=extra_views,
                                  pose=posemap.get(cut),
                                  styling=styling, kind=kind)

            print("    · %s 생성 중…" % LABEL[cut], end=" ", flush=True)
            t0 = time.time()
            try:
                blob = generate(prompt, refs, ASPECT[cut], args.size, args.model)
            except Exception as e:
                print("❌ %s" % str(e)[:140])
                row["상태"] = "실패"; row["오류"] = str(e)[:300]
                cut_fail = True
                break
            path = os.path.join(outdir, cut + ext_for(blob))
            with open(path, "wb") as f:
                f.write(blob)
            row[cut] = path
            note = "%.0f초 · %.1fMB" % (time.time() - t0, len(blob) / 1048576.0)

            if cut == "hero":
                hero_ref = data_url(blob)
            if args.imgbb:
                url = imgbb_upload(blob, "%s-%s" % (safe_dir(j["제품명"]), cut))
                if url:
                    row[cut] = url
                    note += " · 업로드 완료"
            print("✅ %s" % note)
            time.sleep(args.sleep)

        if not cut_fail:
            row["상태"] = "성공"; ok_all += 1
        else:
            fail_all += 1
        rows.append(row)
        save_results(res_path, rows)        # 상품마다 저장
        print()

    print("─" * 62)
    print(" 성공 %d · 실패 %d" % (ok_all, fail_all))
    print(" 이미지: %s" % os.path.join(folder, "out"))
    print(" 목록  : %s" % res_path)
    print("─" * 62)


if __name__ == "__main__":
    main()
