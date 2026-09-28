#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모델 선택지 아이콘
==================
선택지 하나마다 40x40 짜리 작은 그림(SVG)을 만든다.

왜 만드나
---------
"계란형 / 하트형 / 다이아몬드형" 을 글자로 읽으면 머리로 한 번 번역해야 한다.
451개를 그렇게 읽으면 고르기 전에 지친다. 모양은 모양으로 보여주는 게 맞다.

어떻게 만드나
-------------
451개를 손으로 그리지 않는다. 축마다 **매개변수 몇 개짜리 함수**를 두고,
선택지는 그 숫자만 바꾼다. 얼굴형 12개는 '이마폭·광대폭·턱폭·길이·각짐'
다섯 숫자로 전부 나온다. 이렇게 해야 선택지를 나중에 늘려도 같이 늘어난다.

그리지 않는 것
--------------
* 지역적 외형 — 사람 얼굴을 인종별 아이콘으로 만드는 일이다. 안 한다.
* 인상 / 인상(보조) / 역할·페르소나 / 패션 스타일 — '청순한'과 '순한'의
  차이를 선으로 그리면 거짓말이 된다. 이건 실제 생성 샘플이라야 한다.
그 축들은 글자 칩으로 두고, ICON_NONE 에 이유를 적어 둔다.
"""

import math

import model_traits as mt

SZ = 40                      # 네모 한 변
CX = CY = SZ / 2

# 그림으로 정직하게 표현할 수 없는 축과 그 이유
ICON_NONE = {
    "region":      "사람 얼굴을 인종별 아이콘으로 만드는 일이라 그리지 않습니다",
    "impression":  "‘청순한’과 ‘순한’의 차이는 선으로 못 그립니다 (실제 샘플컷 필요)",
    "impression2": "위와 같음",
    "persona":     "직업은 옷·소품으로만 드러나서 얼굴 아이콘으로는 구분이 안 됩니다",
    "fashion":     "옷차림은 모델 아이콘이 아니라 옷 사진으로 보여줘야 맞습니다",
}


# ═══════════════════════════════════════════════════════ 그리기 도우미
def _cr(pts, closed=True, t=1.0):
    """점들을 부드러운 곡선으로 잇는다 (Catmull-Rom → 베지에).

    t 는 팽팽함. 1.0 이면 둥글고, 0 에 가까우면 각진다.
    얼굴형의 '각진형'과 '둥근형'을 같은 점으로 만들 수 있는 이유다.
    """
    n = len(pts)
    if n < 3:
        return ""
    idx = (lambda i: pts[i % n]) if closed else (lambda i: pts[max(0, min(n - 1, i))])
    d = "M%.2f %.2f" % pts[0]
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0, p1, p2, p3 = idx(i - 1), idx(i), idx(i + 1), idx(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * t, p1[1] + (p2[1] - p0[1]) / 6 * t)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * t, p2[1] - (p3[1] - p1[1]) / 6 * t)
        d += "C%.2f %.2f %.2f %.2f %.2f %.2f" % (c1 + c2 + p2)
    return d + ("Z" if closed else "")


def _svg(body, extra=""):
    return ('<svg viewBox="0 0 %d %d" %s>%s</svg>' % (SZ, SZ, extra, body))


def _face_pts(top=10.5, mid=12.5, jaw=9.0, chin=33.0, crown=7.0):
    """얼굴 바깥선을 만드는 점들. 폭 세 개와 길이로 얼굴형이 결정된다."""
    return [
        (CX, crown),
        (CX + top, crown + 4.5),
        (CX + mid, 19.0),
        (CX + jaw, (19.0 + chin) / 2 + 1),
        (CX, chin),
        (CX - jaw, (19.0 + chin) / 2 + 1),
        (CX - mid, 19.0),
        (CX - top, crown + 4.5),
    ]


def _face(fill="#f0e2d6", stroke="#c9b3a3", **kw):
    t = kw.pop("t", 1.0)
    return ('<path d="%s" fill="%s" stroke="%s" stroke-width="1.1"/>'
            % (_cr(_face_pts(**kw), t=t), fill, stroke))


def _eye_at(x, y, w=4.2, h=2.6, tilt=0.0, t=1.0, lid=None, color="#3b2a20"):
    """눈 하나. tilt 는 눈꼬리 높이차(양수면 올라감)."""
    pts = [(x - w, y + tilt * 0.5), (x, y - h), (x + w, y - tilt * 0.5), (x, y + h)]
    out = ('<path d="%s" fill="#fff" stroke="#6b5647" stroke-width="1"/>'
           '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>'
           % (_cr(pts, t=t), x, y, min(h * 0.85, 1.9), color))
    if lid:                                   # 쌍꺼풀 선
        out += ('<path d="M%.1f %.1f Q%.1f %.1f %.1f %.1f" fill="none" '
                'stroke="#b39e8d" stroke-width="%.1f"/>'
                % (x - w * 0.8, y - h - lid[0], x, y - h - lid[0] - 1.4,
                   x + w * 0.8, y - h - lid[0] + tilt * 0.4, lid[1]))
    return out


def _brow_at(x, y, w=5.0, th=1.4, arch=1.2, tilt=0.0, angular=False, op=1.0):
    pts = [(x - w, y + tilt), (x - w * 0.35, y - arch), (x + w * 0.4, y - arch * 0.7),
           (x + w, y + 0.6 - tilt)]
    return ('<path d="%s" fill="none" stroke="#5a4334" stroke-width="%.1f" '
            'stroke-linecap="round" opacity="%.2f"/>'
            % (_cr(pts, closed=False, t=0.2 if angular else 1.0), th, op))


def _both(fn, **kw):
    """좌우 대칭으로 두 번 그린다. 오른쪽은 기울기를 뒤집는다."""
    a = dict(kw); b = dict(kw)
    if "tilt" in kw:
        b["tilt"] = kw["tilt"]
    return fn(CX - 5.6, **a) + fn(CX + 5.6, **b)


# ═══════════════════════════════════════════════════════ 1. 색 스와치
SKIN = {
    "매우 밝음": "#f7e4d7", "밝음": "#f2d8c6", "라이트 베이지": "#e8c4a8",
    "미디엄 베이지": "#d9a97f", "탄": "#c68a5c", "라이트 브라운": "#ab6f45",
    "미디엄 브라운": "#8a5533", "딥 브라운": "#653c24", "매우 짙음": "#432618",
}
UNDERTONE = {"쿨 핑크": "#f0c8c8", "쿨": "#e2c6cc", "뉴트럴": "#ddc9bb",
             "웜": "#e8c49a", "골든": "#e5b878", "올리브": "#c4bd90"}
IRIS = {"블랙": "#1c1512", "다크브라운": "#3b2418", "브라운": "#6b4326",
        "라이트브라운": "#9a6b3c", "헤이즐": "#8b7539", "그린": "#5c7a4a",
        "블루": "#5c7f9e", "그레이": "#8a9099"}
HAIR = {
    "제트 블랙": "#0b0b0d", "블랙": "#14100f", "내추럴 블랙": "#1d1815",
    "다크 초콜릿 브라운": "#2b1b13", "다크 브라운": "#3a2418",
    "내추럴 브라운": "#4a3122", "초콜릿 브라운": "#5a3a24",
    "밀크 브라운": "#7b563a", "라이트 브라운": "#946a45",
    "애쉬 블랙": "#1e1e20", "애쉬 브라운": "#4b4038", "애쉬 베이지": "#a2907c",
    "애쉬 그레이": "#8d8a86", "다크 블론드": "#8a6b42", "허니 블론드": "#c39a5c",
    "골든 블론드": "#d4ab5c", "베이지 블론드": "#d7c49c", "애쉬 블론드": "#c6bda8",
    "플래티넘 블론드": "#e6e0d2", "레드 브라운": "#6e2f22", "코퍼": "#9c4a25",
    "오렌지 코퍼": "#c05f22", "와인": "#5e1f2c", "버건디": "#48141f",
    "핑크": "#d munched", "블루": "#2f4f8a", "퍼플": "#5b3a7e",
    "그린": "#3d6b4a", "실버": "#c2c4c6", "화이트": "#eeece6",
}
HAIR["핑크"] = "#d4657f"
LIP = {"누드 베이지": "#c99a82", "누드 핑크": "#d4a0a0", "피치": "#e8977a",
       "코랄": "#e8705c", "핑크": "#e0728f", "로즈": "#c4566c", "모브": "#a5697e",
       "브릭": "#a8442f", "오렌지 레드": "#d9402a", "클래식 레드": "#c3132a",
       "버건디": "#7d1f2e", "브라운": "#8a5240"}
MK_TONE = {"뉴트럴": "#cdb3a2", "웜 베이지": "#d9b183", "피치": "#f0a98a",
           "코랄": "#ee8a72", "오렌지": "#ef8340", "골드": "#d4a94b",
           "쿨 핑크": "#eda3bb", "로지": "#d4798c", "모브": "#a8798e",
           "브라운": "#8f6249", "레드": "#cf2f3c", "그레이·쿨": "#9aa0a8",
           "모노크롬": "#57585c"}

COLOR_AX = {"skin": SKIN, "undertone": UNDERTONE, "iris": IRIS,
            "hair_color": HAIR, "lip_color": LIP, "mk_tone": MK_TONE}


def _chip(hexv, ring=False):
    """색 하나를 꽉 채운 네모. 밝은 색은 테두리가 있어야 보인다."""
    body = '<rect x="2" y="2" width="36" height="36" rx="9" fill="%s"/>' % hexv
    if ring:
        body += ('<rect x="2.6" y="2.6" width="34.8" height="34.8" rx="8.6" '
                 'fill="none" stroke="#00000022" stroke-width="1"/>')
    return _svg(body)


_IRIS_N = [0]


def _iris_chip(hexv):
    """눈동자 색.

    홍채를 크게 그리고 동공을 그 안에 작게 넣는다. 반대로 하면 (처음에 그랬다)
    동공이 홍채를 덮어서 여덟 색이 전부 까맣게 보인다.

    clipPath 이름은 칸마다 새로 짓는다. 한 화면에 여덟 개가 같이 뜨는데
    이름이 같으면 뒤의 것이 앞의 것을 참조해서 눈이 엉뚱하게 잘린다.
    """
    _IRIS_N[0] += 1
    cid = "iris%d" % _IRIS_N[0]
    eye = _cr([(CX - 12.5, CY), (CX, CY - 7.6), (CX + 12.5, CY), (CX, CY + 7.6)],
              t=1.0)
    r = 6.4
    tpl = (
        '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
        '<defs><clipPath id="{cid}"><path d="{eye}"/></clipPath></defs>'
        '<path d="{eye}" fill="#fdfbf8" stroke="#6b5647" stroke-width="1.1"/>'
        '<g clip-path="url(#{cid})">'
        '<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}"/>'
        '<circle cx="{cx}" cy="{cy}" r="{r2}" fill="none" stroke="#00000055" '
        'stroke-width="1.1"/>'
        '<circle cx="{cx}" cy="{cy}" r="2.5" fill="#100b08"/>'
        '<circle cx="{hx}" cy="{hy}" r="1.5" fill="#ffffffdd"/></g>')
    return _svg(tpl.format(cid=cid, eye=eye, cx=CX, cy=CY, r=r, r2=r - .55,
                           col=hexv, hx=CX - 2.2, hy=CY - 2.4))


def _lip_chip(hexv):
    """립 색상. 큐피드보우가 있는 제대로 된 입술 모양이라야 색이 제 값으로 보인다."""
    L, R, Y = CX - 9.6, CX + 9.6, 20.0          # 좌우 입꼬리와 입선 높이
    upper = (
        "M%.1f %.1f "
        "C%.1f %.1f %.1f %.1f %.1f %.1f "        # 왼쪽 → 왼쪽 봉우리
        "Q%.1f %.1f %.1f %.1f "                  # 가운데 홈 → 오른쪽 봉우리
        "C%.1f %.1f %.1f %.1f %.1f %.1f "        # 오른쪽 봉우리 → 오른쪽 입꼬리
        "C%.1f %.1f %.1f %.1f %.1f %.1f Z"       # 입선을 따라 되돌아옴
        % (L, Y,
           L + 2.6, 17.2, CX - 4.6, 16.0, CX - 2.6, 16.1,
           CX, 17.6, CX + 2.6, 16.1,
           CX + 4.6, 16.0, R - 2.6, 17.2, R, Y,
           CX + 4.2, 19.1, CX - 4.2, 19.1, L, Y))
    lower = (
        "M%.1f %.1f "
        "C%.1f %.1f %.1f %.1f %.1f %.1f "
        "C%.1f %.1f %.1f %.1f %.1f %.1f "
        "C%.1f %.1f %.1f %.1f %.1f %.1f Z"
        % (L, Y,
           L + 1.8, 24.6, CX - 4.4, 26.6, CX, 26.6,
           CX + 4.4, 26.6, R - 1.8, 24.6, R, Y,
           CX + 4.2, 20.6, CX - 4.2, 20.6, L, Y))
    return _svg('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
                '<path d="%s" fill="%s"/><path d="%s" fill="%s"/>'
                '<path d="M%.1f %.1f C%.1f %.1f %.1f %.1f %.1f %.1f" fill="none" '
                'stroke="#00000044" stroke-width=".9"/>'
                % (lower, hexv, upper, hexv,
                   L, Y, CX - 4.2, 19.3, CX + 4.2, 19.3, R, Y))


# ═══════════════════════════════════════════════════════ 2. 얼굴형·부위
FACE_SHAPE = {   # (이마, 광대, 턱, 턱끝y, 각짐)
    "둥근형":          (11.0, 12.8, 10.6, 31.0, 1.0),
    "계란형":          (10.6, 12.2, 9.0, 33.0, 1.0),
    "타원형":          (10.0, 11.6, 8.6, 34.5, 1.0),
    "긴형":            (9.6, 10.8, 8.4, 35.5, 1.0),
    "하트형":          (12.4, 11.8, 7.2, 33.5, 0.9),
    "역삼각형":        (12.8, 11.2, 6.4, 33.0, 0.6),
    "사각형":          (11.8, 12.4, 11.6, 32.0, 0.35),
    "각진형":          (11.4, 12.0, 11.0, 32.5, 0.15),
    "다이아몬드형":    (9.2, 13.2, 8.2, 33.5, 0.5),
    "광대가 도드라진형": (10.2, 13.6, 9.0, 33.0, 0.9),
    "턱선이 뚜렷한형":  (11.0, 12.2, 10.2, 33.0, 0.3),
    "갸름한형":        (9.8, 11.0, 7.4, 34.0, 1.0),
}


def _face_icon(key, name):
    top, mid, jaw, chin, t = FACE_SHAPE[name]
    body = _face(top=top, mid=mid, jaw=jaw, chin=chin, t=t)
    # 이 축이 가리키는 부위를 점선으로 짚어 준다
    return _svg(body)


JAWLINE = {"부드러움": (10.8, 32.0, 1.0), "갸름함": (8.0, 33.5, 1.0),
           "각짐": (11.4, 32.0, 0.15), "뚜렷함": (10.6, 32.5, 0.35)}
CHIN = {"짧은 턱": (9.4, 30.5, .9), "보통": (9.4, 33.0, .9), "긴 턱": (9.4, 35.5, .9),
        "뾰족한 턱": (6.6, 34.0, .9), "넓은 턱": (12.4, 32.5, .5)}
CHEEK = {"낮음": 11.2, "보통": 12.4, "도드라짐": 13.6, "높은 광대": 14.2}


def _marked_face(jaw=9.4, chin=33.0, t=1.0, mid=12.4, mark=None):
    body = _face(mid=mid, jaw=jaw, chin=chin, t=t)
    if mark == "jaw":
        body += ('<path d="M%.1f 22 Q%.1f %.1f %.1f %.1f" fill="none" '
                 'stroke="#4b62ed" stroke-width="1.6" stroke-linecap="round"/>'
                 % (CX - mid + .4, CX - jaw, chin - 2, CX, chin - .4))
    if mark == "chin":
        body += ('<circle cx="%.1f" cy="%.1f" r="3.4" fill="none" '
                 'stroke="#4b62ed" stroke-width="1.5"/>' % (CX, chin - 2.2))
    if mark == "cheek":
        body += ('<circle cx="%.1f" cy="18.5" r="2.4" fill="#4b62ed" opacity=".8"/>'
                 '<circle cx="%.1f" cy="18.5" r="2.4" fill="#4b62ed" opacity=".8"/>'
                 % (CX - mid + 3.2, CX + mid - 3.2))
    return _svg(body)


# ═══════════════════════════════════════════════════════ 3. 눈·눈썹
EYE_SHAPE = {"둥근 눈": (4.0, 3.4, 0.0, 1.0), "아몬드형": (5.0, 2.6, 0.5, 1.0),
             "가로로 긴 눈": (6.0, 2.0, 0.2, 1.0), "세로로 큰 눈": (4.2, 3.8, 0.0, 1.0),
             "눈꼬리가 올라감": (5.0, 2.6, 1.8, 1.0),
             "눈꼬리가 내려감": (5.0, 2.6, -1.8, 1.0),
             "깊게 들어간 눈": (4.8, 2.2, 0.3, 0.45)}
EYE_SIZE = {"작음": (3.6, 2.0), "보통": (4.6, 2.8), "큼": (5.6, 3.6)}
EYELID = {"무쌍": None, "속쌍": (0.3, 0.7), "얇은 쌍꺼풀": (1.1, 0.9),
          "뚜렷한 쌍꺼풀": (1.9, 1.5)}
BROW_THICK = {"얇음": 1.0, "보통": 1.8, "두꺼움": 3.0}
BROW_SHAPE = {"일자": (0.1, 0.0, False), "완만한 아치": (1.1, 0.0, False),
              "뚜렷한 아치": (2.4, 0.0, False), "각진형": (2.0, 0.0, True),
              "자연형": (1.4, 0.3, False)}
BROW_FIN = {"연함": 0.3, "내추럴": 0.55, "결 강조": 0.72, "선명함": 0.88, "진함": 1.0}


def _eyes_icon(key, name):
    bg = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
    if key == "eye_shape":
        w, h, tilt, t = EYE_SHAPE[name]
        g = (_eye_at(CX - 8, CY + 1, w, h, tilt, t, None)
             + _eye_at(CX + 8, CY + 1, w, h, -tilt, t, None))
    elif key == "eye_size":
        w, h = EYE_SIZE[name]
        g = _eye_at(CX - 8, CY + 1, w, h) + _eye_at(CX + 8, CY + 1, w, h)
    elif key == "eyelid":
        lid = EYELID[name]
        g = (_eye_at(CX - 8, CY + 2.5, 4.8, 2.6, 0.4, 1.0, lid)
             + _eye_at(CX + 8, CY + 2.5, 4.8, 2.6, -0.4, 1.0, lid))
    elif key == "brow_thick":
        th = BROW_THICK[name]
        g = (_brow_at(CX - 8, CY + 2, 6.0, th) + _brow_at(CX + 8, CY + 2, 6.0, th)
             + _eye_at(CX - 8, CY + 8, 4.2, 2.2) + _eye_at(CX + 8, CY + 8, 4.2, 2.2))
    elif key == "brow_shape":
        arch, tilt, ang = BROW_SHAPE[name]
        g = (_brow_at(CX - 8, CY + 3, 6.4, 2.0, arch, tilt, ang)
             + _brow_at(CX + 8, CY + 3, 6.4, 2.0, arch, -tilt, ang))
    elif key == "brow_finish":
        op = BROW_FIN[name]
        g = (_brow_at(CX - 8, CY + 3, 6.4, 2.2, 1.4, 0, False, op)
             + _brow_at(CX + 8, CY + 3, 6.4, 2.2, 1.4, 0, False, op))
    else:
        return None
    return _svg(bg + g)


# ═══════════════════════════════════════════════════════ 4. 코·입
NOSE_SIZE = {"작음": (2.6, 6.0), "보통": (3.6, 8.0), "큼": (4.8, 10.0)}
NOSE_SHAPE = {   # (콧볼폭, 길이, 콧대굵기, 콧대휨, 코끝반경)
    "짧은 코": (3.6, 6.0, 1.2, 0, 1.6), "긴 코": (3.6, 11.5, 1.2, 0, 1.6),
    "직선형": (3.6, 9.0, 1.4, 0, 1.4), "곡선형": (3.6, 9.0, 1.4, 1.8, 1.7),
    "코끝이 둥근형": (3.8, 9.0, 1.3, 0, 2.4), "코끝이 뾰족한형": (3.2, 9.0, 1.3, 0, 0.9),
    "콧대가 낮은형": (3.8, 9.0, 0.7, 0, 1.8), "콧대가 높은형": (3.4, 9.0, 2.4, 0, 1.6),
    "콧볼이 좁은형": (2.4, 9.0, 1.3, 0, 1.5), "콧볼이 넓은형": (5.4, 9.0, 1.3, 0, 1.8),
}


def _nose_icon(key, name):
    bg = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
    if key == "nose_size":
        wing, ln = NOSE_SIZE[name]; bridge, bend, tip = 1.3, 0, wing * 0.45
    else:
        wing, ln, bridge, bend, tip = NOSE_SHAPE[name]
    # 40px 안에서 코만 그리면 너무 작아 구분이 안 된다. 1.7배로 키운다.
    K = 1.7
    wing, ln, bridge, tip = wing * K, ln * K, bridge * K, tip * K
    bend *= K
    top = CY - ln / 2 - 1
    bot = top + ln
    g = ('<path d="M%.1f %.1f Q%.1f %.1f %.1f %.1f" fill="none" stroke="#b39779" '
         'stroke-width="%.1f" stroke-linecap="round"/>'
         % (CX, top, CX - bend, (top + bot) / 2, CX, bot, bridge))
    g += ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#f0dcc6" stroke="#96795c" '
          'stroke-width="1.3"/>' % (CX, bot, tip))
    for s in (-1, 1):
        g += ('<path d="M%.1f %.1f Q%.1f %.1f %.1f %.1f" fill="none" '
              'stroke="#96795c" stroke-width="1.3" stroke-linecap="round"/>'
              % (CX + s * tip * .8, bot + tip * .7, CX + s * wing, bot + tip * .5,
                 CX + s * wing * .82, bot - tip * .5))
    return _svg(bg + g)


MOUTH_SIZE = {"작음": 5.2, "보통": 7.2, "큼": 9.4}
LIP_THICK = {"얇음": (1.1, 1.5), "보통": (1.8, 2.5), "도톰함": (2.6, 3.6),
             "매우 도톰함": (3.4, 4.8)}
LIP_SHAPE = {   # (윗두께, 아랫두께, 입꼬리y차, 큐피드보우 깊이)
    "윗입술 얇음": (1.1, 3.2, 0, .8), "아랫입술 도톰": (1.8, 4.4, 0, .8),
    "균형형": (2.4, 2.6, 0, .8), "입꼬리 올라감": (2.0, 2.8, -1.5, .8),
    "입꼬리 내려감": (2.0, 2.8, 1.5, .8), "큐피드보우 뚜렷": (2.4, 2.8, 0, 2.2),
}


def _mouth_icon(key, name):
    bg = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
    if key == "mouth_size":
        w = MOUTH_SIZE[name]; up, lo, corner, bow = 2.0, 2.6, 0, 0.8
    elif key == "lip_thick":
        up, lo = LIP_THICK[name]; w, corner, bow = 7.4, 0, 0.8
    else:
        up, lo, corner, bow = LIP_SHAPE[name]; w = 7.4
    col = "#cc7a7f"
    top = CY - 1
    upper = _cr([(CX, top - up + bow * .5), (CX + w * .45, top - up * .5),
                 (CX + w, top + corner), (CX + w * .5, top - .3),
                 (CX, top - up * .35 - bow * .4), (CX - w * .5, top - .3),
                 (CX - w, top + corner), (CX - w * .45, top - up * .5)], t=.9)
    lower = _cr([(CX - w, top + corner), (CX - w * .5, top + lo * .9),
                 (CX, top + lo * 1.35), (CX + w * .5, top + lo * .9),
                 (CX + w, top + corner), (CX, top + .4)], t=.9)
    return _svg(bg + '<path d="%s" fill="%s"/><path d="%s" fill="%s"/>'
                % (upper, col, lower, col)
                + '<path d="M%.1f %.1f Q%.1f %.1f %.1f %.1f" fill="none" '
                  'stroke="#8f4f55" stroke-width=".9"/>'
                  % (CX - w, top + corner, CX, top + .6, CX + w, top + corner))


# ═══════════════════════════════════════════════════════ 5. 머리
HAIR_TEX = {"완전 직모": (0, 0), "자연 직모": (0.5, 14), "약한 C컬": (1.0, 9),
            "굵은 C컬": (1.8, 8), "자연 웨이브": (1.6, 6.5), "굵은 웨이브": (2.6, 6),
            "잔 웨이브": (1.2, 3.4), "약한 곱슬": (1.9, 3.0), "곱슬": (2.6, 2.3),
            "강한 컬": (3.2, 1.8)}
BANGS = {"없음": "none", "풀뱅": "full", "시스루뱅": "see", "사이드뱅": "side",
         "커튼뱅": "curtain", "처피뱅": "choppy", "긴 앞머리": "long",
         "옆으로 넘김": "swept"}


HAIR_LEN = {"삭발": 13.0, "매우 짧음": 15.0, "숏컷": 18.0, "귀 아래": 22.0,
            "턱선 단발": 27.0, "어깨 단발": 31.0, "쇄골": 34.0, "가슴 위": 36.5,
            "가슴": 38.5, "허리": 40.5}


def _hair_back(bot, w=11.6, amp=0.0, per=0.0, flare=1.0, tone="#33251b"):
    """얼굴 **뒤에** 깔리는 머리 덩어리. 아래로 얼마나 내려오는지가 길이다.

    얼굴을 먼저 그리고 그 위에 덮으면 길이가 하나도 안 보인다.
    뒤 → 얼굴 → 앞(가르마·앞머리) 순서로 쌓아야 한다.
    """
    top, steps = 5.6, 9
    left, right = [], []
    for i in range(steps + 1):
        f = i / steps
        y = 9.0 + (bot - 9.0) * f
        ww = w * (1 + (flare - 1) * f)
        if per:
            ww += math.sin(f * (bot - 9.0) / per * math.pi * 2) * amp
        left.append((CX - ww, y))
        right.append((CX + ww, y))
    pts = ([(CX, top)] + left + [(CX, bot + 1.4)] + right[::-1])
    return '<path d="%s" fill="%s"/>' % (_cr(pts, t=.92), tone)


def _hair_cap(tone="#33251b", lift=0.0, w=11.4):
    """이마를 덮는 앞쪽 덮개. 볼륨은 이걸 들어 올려서 표현한다."""
    return ('<path d="%s" fill="%s"/>'
            % (_cr([(CX, 5.0 - lift), (CX + w, 10.6), (CX + w - .8, 15.6),
                    (CX, 13.0), (CX - w + .8, 15.6), (CX - w, 10.6)], t=1.0), tone))


def _hair_icon(key, name):
    ln, amp, per, flare = 27.0, 0.0, 0.0, 1.0
    bang, tone, lift, w = "none", "#33251b", 0.0, 11.6

    if key == "hair_length":
        ln = HAIR_LEN[name]
        if name == "삭발":
            tone = "#6d5a4b"                      # 두피가 비쳐 밝게 보인다
    elif key == "hair_texture":
        amp, per = HAIR_TEX[name]
        ln = 33.0                                 # 질감은 길어야 보인다
    elif key == "bangs":
        bang = BANGS[name]
        ln = 29.0
    elif key == "hair_thick":
        ln, per, amp = 31.0, 0, 0
        w = {"가늘음": 10.4, "보통": 11.6, "굵음": 12.8}[name]
    elif key == "hair_volume":
        ln = 30.0
        spread = {"적음": .96, "보통": 1.12, "풍성함": 1.34}[name]
        lift = {"적음": 0, "보통": 1.0, "풍성함": 2.4}[name]
        w = {"적음": 10.6, "보통": 11.8, "풍성함": 13.2}[name]
        flare = spread

    g = _hair_back(ln, w, amp, per, flare, tone)
    g += _face(crown=8.5, chin=30.0)
    g += _hair_cap(tone, lift, min(w, 11.8))

    if key == "hair_thick":
        # 가닥은 **머리카락 위에만** 긋는다. 얼굴을 가로지르면 창살처럼 보인다.
        st = {"가늘음": .7, "보통": 1.4, "굵음": 2.3}[name]
        for s in (-1, 1):
            for dx in (0.0, 2.0):
                g += ('<path d="M%.1f 13 Q%.1f 21 %.1f 29" stroke="#1a1108" '
                      'stroke-width="%.1f" fill="none" opacity=".45" '
                      'stroke-linecap="round"/>'
                      % (CX + s * (w - 1.4 - dx), CX + s * (w - .8 - dx),
                         CX + s * (w - 1.8 - dx), st))

    if bang == "full":
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 10.8, 12), (CX, 9.5), (CX + 10.8, 12),
                      (CX + 9.5, 19.5), (CX, 18.2), (CX - 9.5, 19.5)], t=.9), tone))
    elif bang == "see":
        g += ('<path d="%s" fill="%s" opacity=".55"/>'
              % (_cr([(CX - 9.5, 12), (CX, 10), (CX + 9.5, 12),
                      (CX + 8.4, 18), (CX, 17), (CX - 8.4, 18)], t=.9), tone))
    elif bang == "side":
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 11, 11), (CX + 6, 9.6), (CX + 10.6, 13),
                      (CX + 4, 18.5), (CX - 8, 16)], t=.9), tone))
    elif bang == "curtain":
        for s in (-1, 1):
            g += ('<path d="%s" fill="%s"/>'
                  % (_cr([(CX + s * .8, 9.6), (CX + s * 10.6, 12),
                          (CX + s * 9.4, 19.5), (CX + s * 4.6, 15)], t=.9), tone))
    elif bang == "choppy":
        for i, x in enumerate(range(-9, 10, 3)):
            h = 17.5 if i % 2 == 0 else 14.6
            g += ('<path d="M%.1f 10.6 L%.1f %.1f L%.1f 10.6 Z" fill="%s"/>'
                  % (CX + x - 1.6, CX + x, h, CX + x + 1.6, tone))
    elif bang == "long":
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 10.4, 11.5), (CX, 9.8), (CX + 10.4, 11.5),
                      (CX + 9, 23.5), (CX, 22), (CX - 9, 23.5)], t=.9), tone))
    elif bang == "swept":
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 11, 12.5), (CX - 2, 9.4), (CX + 10.8, 11.5),
                      (CX + 11.4, 15), (CX - 2, 13.6), (CX - 9.6, 16)], t=.9), tone))
    return _svg(g)


DYE = {"전체 단색": [("#3a2a1f", 0, 40)], "자연 모발": [("#2e2018", 0, 40)],
       "뿌리 어두움": [("#141010", 0, 14), ("#8a6440", 14, 40)],
       "옴브레": [("#2e2018", 0, 18), ("#6b4a2c", 18, 27), ("#b08a56", 27, 40)],
       "발레아쥬": [("#2e2018", 0, 22), ("#7d5staff", 22, 40)],
       "하이라이트": [("#3a2a1f", 0, 40)], "투톤": [("#1a1412", 0, 20), ("#8a3a52", 20, 40)]}
DYE["발레아쥬"] = [("#2e2018", 0, 21), ("#8a6440", 21, 40)]


_DYE_N = [0]


def _dye_icon(name):
    """염색 방식. 위가 뿌리, 아래가 모발 끝. 칸을 꽉 채운다.

    그라디언트 id 는 칸마다 새로 짓는다. 한 페이지에 같은 id 가 여럿이면
    뒤에 그린 것이 앞의 것을 참조해서 엉뚱한 색이 나온다.
    """
    _DYE_N[0] += 1
    gid = "dye%d" % _DYE_N[0]
    g = ""
    if name in ("옴브레", "발레아쥬"):
        # 색이 위에서 아래로 번진다 — 띠로는 표현이 안 된다
        g = ('<defs><linearGradient id="%s" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#241a14"/>'
             '<stop offset=".45" stop-color="#6b4a2c"/>'
             '<stop offset="1" stop-color="#cba066"/></linearGradient></defs>'
             '<rect x="0" y="0" width="40" height="40" fill="url(#%s)"/>' % (gid, gid))
        if name == "발레아쥬":
            g += ('<path d="M0 24 Q8 17 16 25 Q26 34 40 25 L40 40 L0 40 Z" '
                  'fill="#d2a76c" opacity=".6"/>')
    else:
        for col, y0, y1 in DYE[name]:
            y0 = 0 if y0 <= 0 else y0
            y1 = 40 if y1 >= 40 else y1
            g += ('<rect x="0" y="%.1f" width="40" height="%.1f" fill="%s"/>'
                  % (y0, y1 - y0, col))
        if name == "자연 모발":                  # 염색 안 한 머리는 색이 고르지 않다
            g += ('<rect x="0" y="0" width="40" height="40" fill="#000" opacity=".22"/>'
                  '<path d="M0 14 Q10 20 20 15 Q30 10 40 16 L40 40 L0 40 Z" '
                  'fill="#5a4230" opacity=".5"/>')
        if name == "하이라이트":
            for x in (7, 15, 23, 31):
                g += ('<rect x="%.1f" y="0" width="2.8" height="40" '
                      'fill="#c99a5c"/>' % x)
    return _svg(g, 'style="border-radius:9px;overflow:hidden"')


STYLING_GLYPH = {
    "자연스럽게 풀기": "down", "깔끔한 스트레이트": "straight",
    "볼륨 스트레이트": "volume", "C컬": "ccurl", "S컬": "scurl", "웨이브": "wave",
    "슬릭백": "slick", "웨트 헤어": "wet", "로우 포니테일": "lowpony",
    "하이 포니테일": "highpony", "로우 번": "lowbun", "하이 번": "highbun",
    "반묶음": "half", "브레이드": "braid", "헝클어진 내추럴": "messy",
    "댄디컷": "dandy", "가르마": "part", "쉼표머리": "comma", "리젠트": "regent",
    "크롭컷": "crop", "버즈컷": "buzz", "포마드": "pomade", "장발": "longm",
}


def _styling_icon(name):
    """스타일링 23개는 길이·묶음·볼륨 세 성질의 조합으로 그린다."""
    g = STYLING_GLYPH[name]
    head = _face(crown=9.0, chin=30.0)
    tone = "#33251b"
    out = ""
    # 짧은 남성컷은 머리가 짧고, 묶는 머리는 뒤로 걷어 올려 옆이 비어 보인다
    ln = {"buzz": 13, "crop": 14.5, "dandy": 16, "part": 17, "comma": 17,
          "regent": 16, "pomade": 16, "slick": 16.5, "wet": 18,
          "longm": 30}.get(g, 32)
    if g in ("lowpony", "highpony", "lowbun", "highbun", "braid"):
        ln = 17
    elif g == "half":
        ln = 30
    # 짧은 컷은 **폭도 같이 줄여야** 짧아 보인다. 길이만 줄이면 얼굴에 가려
    # 버즈컷과 장발이 똑같이 보인다 (처음에 그렇게 만들었다가 고쳤다).
    w = {"buzz": 9.4, "crop": 10.0, "dandy": 10.5, "regent": 10.6,
         "pomade": 10.6, "slick": 10.6, "part": 10.9, "comma": 10.9,
         "wet": 11.0}.get(g, 11.6)
    if g in ("volume", "messy"):
        w = 13.4
    lift = 2.0 if g in ("volume", "regent", "pomade") else 0
    # 뒤 → 얼굴 → 앞 순서. 얼굴을 먼저 그리면 머리가 안 보인다.
    out += _hair_back(ln, w, 0, 0, 1.0, tone)
    out += head
    out += _hair_cap(tone, lift, w)
    # 묶음 표시
    if g == "highpony":
        out += ('<circle cx="30" cy="10" r="4.6" fill="%s"/>'
                '<path d="M30 10 Q36 16 33 26" stroke="%s" stroke-width="3.4" '
                'fill="none" stroke-linecap="round"/>' % (tone, tone))
    elif g == "lowpony":
        out += ('<path d="M28 24 Q34 28 32 36" stroke="%s" stroke-width="3.6" '
                'fill="none" stroke-linecap="round"/>' % tone)
    elif g == "highbun":
        out += '<circle cx="20" cy="5.4" r="4.8" fill="%s"/>' % tone
    elif g == "lowbun":
        out += '<circle cx="20" cy="30.5" r="4.6" fill="%s"/>' % tone
    elif g == "half":
        out += ('<path d="M13 12 Q20 16 27 12" stroke="#f6f3ef" stroke-width="1.4" '
                'fill="none"/><circle cx="20" cy="15.6" r="2.2" fill="%s"/>' % tone)
    elif g == "braid":
        for i in range(4):
            out += ('<circle cx="%.1f" cy="%.1f" r="2.5" fill="%s"/>'
                    % (CX + (1.6 if i % 2 else -1.6), 20 + i * 4.4, tone))
    elif g in ("slick", "pomade", "wet"):
        out += ('<path d="M11 11 Q20 7.4 29 11" stroke="#ffffff88" '
                'stroke-width="1.6" fill="none"/>')
    elif g == "part":
        out += '<path d="M20 5.6 L20 13.4" stroke="#f6f3ef" stroke-width="1.5"/>'
    elif g == "comma":
        out += ('<path d="M12 12 Q17 17 13 19" stroke="%s" stroke-width="2.6" '
                'fill="none" stroke-linecap="round"/>' % tone)
    elif g == "regent":
        out += ('<path d="M12 10 Q20 2.6 28 9" fill="%s"/>' % tone)
    elif g in ("ccurl", "scurl", "wave"):
        amp = {"ccurl": 1.6, "scurl": 2.4, "wave": 2.8}[g]
        for s in (-1, 1):
            out += ('<path d="M%.1f 20 Q%.1f 24 %.1f 27 Q%.1f 30 %.1f 33" '
                    'stroke="%s" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
                    % (CX + s * 11, CX + s * (11 + amp), CX + s * 11,
                       CX + s * (11 - amp), CX + s * 11.4, tone))
    elif g == "messy":
        for x, y in ((8, 12), (31, 13), (10, 20), (30, 21)):
            out += ('<path d="M%d %d l3 -3" stroke="%s" stroke-width="1.6" '
                    'stroke-linecap="round"/>' % (x, y, tone))
    return _svg(out)


# ═══════════════════════════════════════════════════════ 6. 몸
def _body(shoulder=8.0, waist=5.0, hip=7.6, thick=1.0, height=1.0, muscle=0.0):
    """상반신 실루엣 하나로 키·체형·근육·어깨·비율·팔다리를 다 그린다."""
    top, bot = 20 - 13 * height, 20 + 15 * height
    head_r = 3.2
    hy = top + head_r
    sh = top + head_r * 2.4
    wy = (sh + bot) * .52
    hipy = (sh + bot) * .68
    s, w, h = shoulder * thick, waist * thick, hip * thick
    s += muscle * 1.8
    pts = [(CX, sh - 1.2), (CX + s, sh + 1.4), (CX + w + muscle, wy),
           (CX + h, hipy), (CX + h * .82, bot), (CX + 1.4, bot),
           (CX, bot - 3), (CX - 1.4, bot), (CX - h * .82, bot),
           (CX - h, hipy), (CX - w - muscle, wy), (CX - s, sh + 1.4)]
    return ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#c9b3a3"/>'
            '<path d="%s" fill="#c9b3a3"/>' % (CX, hy, head_r, _cr(pts, t=.95)))


HEIGHT = {"매우 작음": .70, "작은 편": .84, "평균": 1.0, "큰 편": 1.12, "매우 큼": 1.24}
BODY = {"매우 마른": (6.6, 3.2, 5.4), "마른": (7.2, 3.9, 6.2), "슬림": (7.7, 4.4, 6.9),
        "보통": (8.2, 5.2, 7.7), "탄탄한": (8.9, 5.4, 8.0), "볼륨 있는": (8.6, 5.0, 9.4),
        "통통한": (9.2, 7.4, 9.6), "플러스 사이즈": (10.2, 9.4, 11.0)}
MUSCLE = {"거의 없음": -.6, "낮음": -.3, "보통": 0, "잔근육": .4, "탄탄함": .9,
          "근육질": 1.5, "매우 근육질": 2.2}
SHOULDER = {"좁음": 6.6, "보통": 8.2, "넓음": 10.2}


def _body_icon(key, name):
    bg = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
    if key == "height":
        g = _body(height=HEIGHT[name])
        g += ('<path d="M4 %.1f L4 %.1f" stroke="#4b62ed" stroke-width="1.3"/>'
              % (20 - 13 * HEIGHT[name], 20 + 15 * HEIGHT[name]))
    elif key == "body":
        s, w, h = BODY[name]; g = _body(s, w, h)
    elif key == "muscle":
        g = _body(muscle=MUSCLE[name])
    elif key == "shoulder":
        g = _body(shoulder=SHOULDER[name])
        g += ('<path d="M%.1f 12.6 L%.1f 12.6" stroke="#4b62ed" stroke-width="1.4" '
              'stroke-linecap="round"/>' % (CX - SHOULDER[name], CX + SHOULDER[name]))
    elif key == "proportion":
        r = {"상체가 긴 편": .60, "균형형": .50, "하체가 긴 편": .40}[name]
        g = _body()
        y = 8 + 26 * r
        g += ('<path d="M6 %.1f L34 %.1f" stroke="#4b62ed" stroke-width="1.2" '
              'stroke-dasharray="2.4 2"/>' % (y, y))
    elif key == "limbs":
        f = {"짧은 편": .72, "평균": 1.0, "긴 편": 1.26}[name]
        g = _body()
        for s in (-1, 1):
            g += ('<path d="M%.1f 13.6 Q%.1f %.1f %.1f %.1f" stroke="#c9b3a3" '
                  'stroke-width="2.6" fill="none" stroke-linecap="round"/>'
                  % (CX + s * 8, CX + s * 12.4, 20, CX + s * 11, 13.6 + 12 * f))
    else:
        return None
    return _svg(bg + g)


# ═══════════════════════════════════════════════════════ 7. 피부결·표현
SKIN_TEX = {"매우 매끈": "smooth", "자연스러운 피부결": "natural",
            "모공이 보이는 자연 피부": "pore", "주근깨": "freckle", "점 있음": "mole",
            "홍조": "flush", "잡티 자연스럽게": "blem"}


def _skintex_icon(name):
    k = SKIN_TEX[name]
    g = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#ecd3bf"/>'
    import random
    rnd = random.Random(hash(name) & 0xffff)
    if k == "smooth":
        g += ('<ellipse cx="14" cy="14" rx="8" ry="6" fill="#ffffff55"/>')
    elif k == "natural":
        for _ in range(26):
            g += ('<circle cx="%.1f" cy="%.1f" r=".5" fill="#00000012"/>'
                  % (rnd.uniform(5, 35), rnd.uniform(5, 35)))
    elif k == "pore":
        for _ in range(60):
            g += ('<circle cx="%.1f" cy="%.1f" r=".62" fill="#00000022"/>'
                  % (rnd.uniform(4, 36), rnd.uniform(4, 36)))
    elif k == "freckle":
        for _ in range(22):
            g += ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#a5703f99"/>'
                  % (rnd.uniform(7, 33), rnd.uniform(9, 31), rnd.uniform(.7, 1.3)))
    elif k == "mole":
        g += ('<circle cx="24.5" cy="16" r="1.9" fill="#4a2c18"/>'
              '<circle cx="15" cy="26" r="1.2" fill="#5c3a22"/>')
    elif k == "flush":
        g += ('<ellipse cx="20" cy="22" rx="12" ry="8" fill="#e08a86" opacity=".55"/>')
    elif k == "blem":
        for _ in range(9):
            g += ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#c07a63" opacity=".5"/>'
                  % (rnd.uniform(8, 32), rnd.uniform(8, 32), rnd.uniform(1.2, 2.4)))
    return _svg(g)


# 광택 정도: 같은 살색 위에 하이라이트 세기만 바꾼다
FINISH = {
    "skin_finish": {"Bare Skin": .06, "내추럴": .16, "글로우": .42, "물광": .68,
                    "세미매트": .10, "매트": .0, "선키스드": .30},
    "mk_base": {"거의 없음": .06, "투명 피부": .20, "내추럴": .18, "글로우": .45,
                "물광": .70, "새틴": .34, "세미매트": .12, "매트": .0, "풀커버": .08},
    "lip_finish": {"거의 없음": .05, "립밤": .30, "틴트": .14, "그라데이션": .18,
                   "풀립": .24, "글로시": .72, "새틴": .40, "매트": .0},
}


def _finish_icon(key, name):
    v = FINISH[key][name]
    base = "#cc7a7f" if key == "lip_finish" else "#e4bb9c"
    matte = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="%s"/>' % base)
    if key == "mk_base" and name == "풀커버":
        matte += '<rect x="2" y="2" width="36" height="36" rx="9" fill="#00000010"/>'
    gloss = ('<ellipse cx="15" cy="14" rx="9" ry="6.4" fill="#fff" opacity="%.2f" '
             'transform="rotate(-18 15 14)"/>'
             '<ellipse cx="27" cy="27" rx="5" ry="3.4" fill="#fff" opacity="%.2f"/>'
             % (v, v * .55))
    if key == "lip_finish" and name == "그라데이션":
        gloss += ('<ellipse cx="20" cy="20" rx="9" ry="9" fill="#a33b47" opacity=".55"/>')
    return _svg(matte + gloss)


MK_LEVEL = {"Bare Face": 0, "No-Makeup Makeup": 1, "매우 연함": 2, "내추럴": 3,
            "데일리": 4, "또렷함": 5, "글래머러스": 6, "강한 메이크업": 7,
            "에디토리얼": 8}
MK_EYE = {"거의 없음": 0, "음영만": 1, "내추럴": 2, "속눈썹 강조": 3,
          "아이라인 강조": 4, "눈꼬리 강조": 5, "브라운 스모키": 6,
          "블랙 스모키": 7, "글리터": 8, "컬러 아이": 9, "그래픽 아이라인": 10}


def _mklevel_icon(name):
    """강도는 얼굴 아이콘 + 채워진 칸 수로 보여준다."""
    n = MK_LEVEL[name]
    g = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
         + _face(crown=7.5, chin=28.0)
         + _eye_at(CX - 5.4, 17, 3.2, 1.9) + _eye_at(CX + 5.4, 17, 3.2, 1.9))
    lip = "#cc7a7f" if n < 5 else "#b02a3a"
    g += ('<ellipse cx="20" cy="23.4" rx="%.1f" ry="%.1f" fill="%s" opacity="%.2f"/>'
          % (3 + n * .25, 1.1 + n * .12, lip, .25 + n * .09))
    if n >= 3:
        g += ('<path d="M%.1f 15 Q%.1f 13.6 %.1f 15" stroke="#3a2a20" '
              'stroke-width="%.1f" fill="none"/>' % (CX - 8.6, CX - 5.4, CX - 2.2,
                                                     .6 + n * .16))
        g += ('<path d="M%.1f 15 Q%.1f 13.6 %.1f 15" stroke="#3a2a20" '
              'stroke-width="%.1f" fill="none"/>' % (CX + 2.2, CX + 5.4, CX + 8.6,
                                                     .6 + n * .16))
    if n >= 6:
        for s in (-1, 1):
            g += ('<ellipse cx="%.1f" cy="21.5" rx="2.6" ry="1.6" fill="#d98a7a" '
                  'opacity=".5"/>' % (CX + s * 8))
    for i in range(9):                                  # 아래 강도 눈금
        g += ('<rect x="%.1f" y="35" width="2.6" height="2.6" rx=".8" fill="%s"/>'
              % (4.4 + i * 3.6, "#4b62ed" if i <= n else "#dcdde3"))
    return _svg(g)


def _mkeye_icon(name):
    n = MK_EYE[name]
    g = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>')
    shade = {6: "#7a4a32", 7: "#2e2422", 9: "#4a5fb0"}.get(n)
    if n in (1, 2) or shade:
        g += ('<ellipse cx="20" cy="15.4" rx="11" ry="5" fill="%s" opacity="%.2f"/>'
              % (shade or "#b08466", .22 if n in (1, 2) else .6))
    g += _eye_at(CX, 20.5, 9.4, 5.4, 1.2 if n == 5 else 0)
    if n >= 3:                                          # 속눈썹
        for i, x in enumerate(range(-7, 8, 3)):
            g += ('<path d="M%.1f %.1f l%.1f -2.6" stroke="#241a14" '
                  'stroke-width="1.2" stroke-linecap="round"/>'
                  % (CX + x, 15.6, .6 + i * .2))
    if n in (4, 5, 10):                                 # 아이라인
        tail = 5 if n in (5, 10) else 2.5
        g += ('<path d="M%.1f 20.4 Q20 14.6 %.1f %.1f" stroke="#141010" '
              'stroke-width="%.1f" fill="none" stroke-linecap="round"/>'
              % (CX - 9.4, CX + 9.4 + tail, 18.6 - tail * .5, 2.4 if n == 10 else 1.6))
    if n == 8:                                          # 글리터
        import random
        rnd = random.Random(7)
        for _ in range(14):
            g += ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#e8c86a"/>'
                  % (rnd.uniform(11, 29), rnd.uniform(12, 18), rnd.uniform(.5, 1.1)))
    return _svg(g)


BEARD = {"없음": 0, "면도 직후": 1, "옅은 스터블": 2, "진한 스터블": 3,
         "콧수염": 4, "턱수염": 5, "짧은 풀비어드": 6, "긴 풀비어드": 7}


def _beard_icon(name):
    n = BEARD[name]
    g = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
         + _face(crown=7.0, chin=30.0)
         + _eye_at(CX - 5.2, 16, 3.0, 1.8) + _eye_at(CX + 5.2, 16, 3.0, 1.8))
    col, op = "#3a2a1f", {0: 0, 1: .18, 2: .38, 3: .72}.get(n, 1)
    if n <= 3:
        if n:
            g += ('<path d="%s" fill="%s" opacity="%.2f"/>'
                  % (_cr([(CX - 9, 21), (CX - 7.4, 27.5), (CX, 30.4),
                          (CX + 7.4, 27.5), (CX + 9, 21), (CX, 24)], t=.9), col, op))
    elif n == 4:
        g += ('<path d="M%.1f 22 Q20 20.4 %.1f 22 Q20 24.4 %.1f 22 Z" fill="%s"/>'
              % (CX - 5.4, CX + 5.4, CX - 5.4, col))
    elif n == 5:
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 5, 26), (CX, 24.6), (CX + 5, 26), (CX + 4, 30.6),
                      (CX, 31.4), (CX - 4, 30.6)], t=.9), col))
    else:
        depth = 30.8 if n == 6 else 36.5
        g += ('<path d="%s" fill="%s"/>'
              % (_cr([(CX - 9.4, 20), (CX - 8.4, 27), (CX, depth),
                      (CX + 8.4, 27), (CX + 9.4, 20), (CX, 23.4)], t=.92), col))
        g += ('<path d="M%.1f 21.6 Q20 19.8 %.1f 21.6 Q20 24 %.1f 21.6 Z" fill="%s"/>'
              % (CX - 5.6, CX + 5.6, CX - 5.6, col))
    return _svg(g)


EXPR = {"무표정": (0, 0), "편안한 표정": (.5, 0), "옅은 미소": (1.2, 0),
        "자연스러운 미소": (2.0, 0), "활짝 웃음": (3.2, 0), "치아 보이는 웃음": (3.4, 1),
        "장난스러운 표정": (2.2, 2), "자신감 있는 표정": (1.4, 3), "진지함": (-.3, 4),
        "차가운 표정": (-.8, 5), "강렬한 눈빛": (0, 6), "놀람": (0, 7),
        "호기심": (.6, 8), "행복": (3.0, 0)}


def _expr_icon(name):
    curve, mode = EXPR[name]
    g = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
         + _face(crown=7.0, chin=31.0))
    eh = 3.4 if mode == 7 else (1.8 if mode in (5, 6) else 2.4)
    tilt = 1.0 if mode == 8 else 0
    g += _eye_at(CX - 5.6, 17.5, 3.4, eh, tilt) + _eye_at(CX + 5.6, 17.5, 3.4, eh, -tilt)
    bt = 2.0 if mode == 6 else (1.4 if mode in (3, 4) else 1.2)
    ba = 2.2 if mode == 7 else (0.3 if mode in (4, 5, 6) else 1.2)
    g += (_brow_at(CX - 5.6, 13.2, 4.4, bt, ba, -0.8 if mode in (4, 6) else 0)
          + _brow_at(CX + 5.6, 13.2, 4.4, bt, ba, -0.8 if mode in (4, 6) else 0))
    if mode == 1:
        g += ('<path d="M%.1f 24 Q20 %.1f %.1f 24 Z" fill="#b8525c"/>'
              '<path d="M%.1f 24.6 Q20 26.6 %.1f 24.6 Z" fill="#fff"/>'
              % (CX - 6, 24 + curve * 1.9, CX + 6, CX - 5, CX + 5))
    elif mode == 2:
        g += ('<path d="M%.1f 24.4 Q%.1f %.1f %.1f 25.6" fill="none" '
              'stroke="#a8515a" stroke-width="1.6" stroke-linecap="round"/>'
              % (CX - 6, CX, 24 + curve * 1.7, CX + 6))
    else:
        g += ('<path d="M%.1f 25 Q20 %.1f %.1f 25" fill="none" stroke="#a8515a" '
              'stroke-width="1.7" stroke-linecap="round"/>'
              % (CX - 5.6, 25 + curve * 1.9, CX + 5.6))
    return _svg(g)


FEATURE = {
    "주근깨": "freckle", "볼 주근깨": "cheekfreckle", "점": "mole", "눈 밑 점": "eyemole",
    "보조개": "dimple", "홍조": "flush", "다크서클": "dark", "애교살": "aegyo",
    "치아 노출 미소": "teeth", "덧니": "snag", "갭투스": "gap", "얼굴 흉터": "scar",
    "피어싱": "pierce", "타투": "tattoo", "안경": "glasses",
}


def _feature_icon(name):
    k = FEATURE[name]
    g = ('<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
         + _face(crown=7.0, chin=31.0)
         + _eye_at(CX - 5.6, 17.5, 3.4, 2.3) + _eye_at(CX + 5.6, 17.5, 3.4, 2.3))
    import random
    rnd = random.Random(hash(k) & 0xffff)
    if k == "freckle":
        for _ in range(16):
            g += ('<circle cx="%.1f" cy="%.1f" r=".9" fill="#9a6535"/>'
                  % (rnd.uniform(12, 28), rnd.uniform(19, 27)))
    elif k == "cheekfreckle":
        for s in (-1, 1):
            for _ in range(7):
                g += ('<circle cx="%.1f" cy="%.1f" r=".9" fill="#9a6535"/>'
                      % (CX + s * rnd.uniform(6, 10), rnd.uniform(20, 25)))
    elif k == "mole":
        g += '<circle cx="25.5" cy="22.5" r="1.6" fill="#3d2313"/>'
    elif k == "eyemole":
        g += '<circle cx="%.1f" cy="21.4" r="1.4" fill="#3d2313"/>' % (CX - 5.6)
    elif k == "dimple":
        for s in (-1, 1):
            g += ('<path d="M%.1f 24.6 q%.1f 1.6 0 3.2" fill="none" stroke="#b89a84" '
                  'stroke-width="1.2" stroke-linecap="round"/>'
                  % (CX + s * 8.4, s * .9))
        g += ('<path d="M%.1f 25 Q20 28.4 %.1f 25" fill="none" stroke="#a8515a" '
              'stroke-width="1.6" stroke-linecap="round"/>' % (CX - 5.6, CX + 5.6))
    elif k == "flush":
        for s in (-1, 1):
            g += ('<ellipse cx="%.1f" cy="22" rx="4.4" ry="2.8" fill="#e08a86" '
                  'opacity=".6"/>' % (CX + s * 7.6))
    elif k == "dark":
        for s in (-1, 1):
            g += ('<path d="M%.1f 20.4 q3.6 2.6 7.2 0" fill="none" stroke="#8d7a94" '
                  'stroke-width="2.2" opacity=".55" stroke-linecap="round"/>'
                  % (CX + s * 5.6 - 3.6))
    elif k == "aegyo":
        for s in (-1, 1):
            g += ('<path d="M%.1f 20.2 q3.6 2.2 7.2 0" fill="none" stroke="#d9a894" '
                  'stroke-width="1.8" stroke-linecap="round"/>' % (CX + s * 5.6 - 3.6))
    elif k in ("teeth", "snag", "gap"):
        g += ('<path d="M%.1f 24 Q20 29.6 %.1f 24 Z" fill="#b8525c"/>'
              '<rect x="%.1f" y="24.3" width="10" height="2.8" rx=".8" fill="#fff"/>'
              % (CX - 6.2, CX + 6.2, CX - 5))
        if k == "snag":
            g += '<path d="M23 24.3 l1.2 3.4 l1.2 -3.4 Z" fill="#fff"/>'
        if k == "gap":
            g += '<rect x="19.4" y="24.3" width="1.3" height="2.8" fill="#b8525c"/>'
    elif k == "scar":
        g += ('<path d="M26 13.5 l-2.6 6.4" stroke="#c48d7a" stroke-width="1.5" '
              'stroke-linecap="round"/>')
    elif k == "pierce":
        g += ('<circle cx="%.1f" cy="15.4" r="1.4" fill="#d8c07a"/>'
              '<circle cx="20" cy="26.6" r="1.2" fill="#d8c07a"/>' % (CX - 10.4))
    elif k == "tattoo":
        g += ('<path d="M25 27 q3 -2.4 5.4 .6 q-2.6 3.4 -5.4 -.6 Z" fill="#4a5fb0" '
              'opacity=".75"/>')
    elif k == "glasses":
        g += ('<rect x="7.6" y="13.6" width="10" height="8" rx="3" fill="none" '
              'stroke="#3a3f4a" stroke-width="1.5"/>'
              '<rect x="22.4" y="13.6" width="10" height="8" rx="3" fill="none" '
              'stroke="#3a3f4a" stroke-width="1.5"/>'
              '<path d="M17.6 17 h4.8" stroke="#3a3f4a" stroke-width="1.5"/>')
    return _svg(g)


SEX = {"여성": "f", "남성": "m", "중성적": "n"}


def _sex_icon(name):
    """성별 표현. 실루엣 차이가 작아서 머리 길이까지 같이 바꿔야 구분된다."""
    k = SEX[name]
    g = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'
    if k == "f":
        g += _hair_back(24.0, 7.2, tone="#33251b")
        g += _body(7.6, 4.2, 9.4)
    elif k == "m":
        g += _body(10.4, 7.2, 7.2)
        g += _hair_cap("#33251b", 0, 3.6).replace("M20.00 5.00", "M20.00 6.20")
    else:
        g += _hair_back(18.0, 6.0, tone="#33251b")
        g += _body(9.0, 5.8, 8.2)
    return _svg(g)


AGE = {"아기 (6~12개월)": .42, "유아 (1~3세)": .52, "아동 (4~6세)": .62,
       "아동 (7~9세)": .72, "주니어 (10~12세)": .84, "20대 초반": 1.0,
       "20대 중반": 1.0, "20대 후반": 1.0, "30대 초반": 1.0, "30대 중반": 1.0,
       "30대 후반": 1.0, "40대": 1.0, "50대": 1.0, "60대": 1.0, "70대+": 1.0}
AGE_YEARS = {"아기 (6~12개월)": 1, "유아 (1~3세)": 2, "아동 (4~6세)": 5,
             "아동 (7~9세)": 8, "주니어 (10~12세)": 11, "20대 초반": 22,
             "20대 중반": 25, "20대 후반": 28, "30대 초반": 32, "30대 중반": 35,
             "30대 후반": 38, "40대": 45, "50대": 55, "60대": 65, "70대+": 75}


def _age_icon(name):
    """연령.

    어린이 다섯 칸은 **머리 대 몸 비율**이 실제로 다르므로 실루엣으로 구분된다.
    어른 열 칸은 실루엣이 사실상 같다. 20대 후반과 30대 초반을 선으로 그려
    구분한 척하면 거짓말이다. 그래서 어른은 머리 세는 정도만 그리고,
    **숫자를 아이콘의 주인공으로** 둔다.
    """
    yr = AGE_YEARS[name]
    g = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'

    if yr < 20:                                   # ── 어린이: 머리 비율로 구분
        f = AGE[name]
        head_r = 3.0 + (1 - f) * 3.6
        top = 29 - 21 * f
        g += ('<circle cx="20" cy="%.1f" r="%.1f" fill="#c9b3a3"/>'
              % (top + head_r, head_r))
        sh = top + head_r * 2.1
        s = 3.4 + 4.6 * f
        g += ('<path d="%s" fill="#c9b3a3"/>'
              % _cr([(CX, sh - 1), (CX + s, sh + 1.4), (CX + s * .76, 29),
                     (CX, 29.6), (CX - s * .76, 29), (CX - s, sh + 1.4)], t=.95))
        g += ('<text x="20" y="37.2" font-size="7" text-anchor="middle" '
              'fill="#4b62ed" font-weight="700" font-family="sans-serif">'
              '%d세</text>' % yr)
        return _svg(g)

    # ── 어른: 머리 세는 정도 + 큰 숫자
    grey = {22: 0, 25: 0, 28: 0, 32: 0, 35: 0, 38: .08,
            45: .18, 55: .42, 65: .72, 75: .92}[yr]
    hair = "#2e2018"
    g += _hair_back(20.5, 8.4, tone=hair)
    g += ('<circle cx="20" cy="13.6" r="6.2" fill="#dcc3ae"/>')
    g += _hair_cap(hair, 0, 6.6).replace('d="M20.00 5.00', 'd="M20.00 6.60')
    if grey:                                      # 흰머리는 덮개 위에 얹는다
        g += ('<path d="%s" fill="#d8d4cd" opacity="%.2f"/>'
              % (_cr([(CX, 6.8), (CX + 6.6, 11.2), (CX + 6.0, 14.4), (CX, 12.6),
                      (CX - 6.0, 14.4), (CX - 6.6, 11.2)], t=1.0), grey))
    g += ('<text x="20" y="34" font-size="13.5" text-anchor="middle" '
          'fill="#2c3550" font-weight="800" font-family="sans-serif" '
          'letter-spacing="-.5">%d</text>' % yr)
    return _svg(g)


# ═══════════════════════════════════════════════════════ 배선
def icon(key, name):
    """선택지 하나의 SVG. 그릴 수 없으면 None 을 돌려준다."""
    if key in ICON_NONE or name == mt.NONE:
        return None
    try:
        if key in COLOR_AX:
            if key == "iris":
                return _iris_chip(IRIS[name])
            if key == "lip_color":
                return _lip_chip(LIP[name])
            return _chip(COLOR_AX[key][name], ring=True)
        if key == "sex":
            return _sex_icon(name)
        if key == "age":
            return _age_icon(name)
        if key == "face":
            return _face_icon(key, name)
        if key == "jawline":
            j, c, t = JAWLINE[name]; return _marked_face(j, c, t, mark="jaw")
        if key == "chin":
            j, c, t = CHIN[name];    return _marked_face(j, c, t, mark="chin")
        if key == "cheekbone":
            return _marked_face(mid=CHEEK[name], mark="cheek")
        if key in ("eye_shape", "eye_size", "eyelid", "brow_thick",
                   "brow_shape", "brow_finish"):
            return _eyes_icon(key, name)
        if key in ("nose_size", "nose_shape"):
            return _nose_icon(key, name)
        if key in ("mouth_size", "lip_thick", "lip_shape"):
            return _mouth_icon(key, name)
        if key in ("hair_length", "hair_texture", "bangs", "hair_thick", "hair_volume"):
            return _hair_icon(key, name)
        if key == "dye":
            return _dye_icon(name)
        if key == "hair_styling":
            return _styling_icon(name)
        if key in ("height", "body", "muscle", "shoulder", "proportion", "limbs"):
            return _body_icon(key, name)
        if key == "skin_texture":
            return _skintex_icon(name)
        if key in FINISH:
            return _finish_icon(key, name)
        if key == "mk_level":
            return _mklevel_icon(name)
        if key == "mk_eye":
            return _mkeye_icon(name)
        if key == "beard":
            return _beard_icon(name)
        if key == "expression":
            return _expr_icon(name)
        if key == "features":
            return _feature_icon(name)
    except KeyError:
        return None
    return None


# ═══════════════════════════════════════════════════ 화면에 넘길 색 목록
# 머리색 30개를 한 줄로 늘어놓으면 고를 수가 없다. 계열로 묶어서 넘긴다.
HAIR_GROUPS = [
    ("블랙", ["제트 블랙", "블랙", "내추럴 블랙", "애쉬 블랙"]),
    ("브라운", ["다크 초콜릿 브라운", "다크 브라운", "내추럴 브라운",
                "초콜릿 브라운", "밀크 브라운", "라이트 브라운"]),
    ("애쉬", ["애쉬 브라운", "애쉬 베이지", "애쉬 그레이"]),
    ("블론드", ["다크 블론드", "허니 블론드", "골든 블론드", "베이지 블론드",
                "애쉬 블론드", "플래티넘 블론드"]),
    ("레드·와인", ["레드 브라운", "코퍼", "오렌지 코퍼", "와인", "버건디"]),
    ("패션", ["핑크", "블루", "퍼플", "그린", "실버", "화이트"]),
]

# 색 격자로 바꿀 축과, 칸을 어떻게 칠할지
#   flat  = 색 한 칸        under = 기준 피부 옆에 붙여 비교
#   hair  = 뿌리·윤기 띠     trio  = 베이스·볼·입술 세 칸
#   art   = 아이콘 그대로 (눈·입술·염색)
SWATCH_KIND = {
    "skin": "flat", "undertone": "under", "hair_color": "hair",
    "mk_tone": "trio", "iris": "art", "lip_color": "art", "dye": "art",
}
# 색 축만 격자로 바꾼다.
#
# 얼굴형·눈·코·머리 모양도 아이콘으로 넣어 봤다가 뺐다. 색은 색으로 보면
# 그것으로 끝이지만, 모양 아이콘은 내가 '계란형이란 이런 것'이라고 해석해서
# 그린 그림이라 실제 결과와 다를 수 있다. 그 축들은 실제 생성 견본 사진이
# 준비되면(model_shots.py) 그때 바꾸는 게 맞다.
#
# 되살리려면 아래 한 줄이면 된다:
#   for _k in ("face","eye_shape","hair_styling",...): SWATCH_KIND.setdefault(_k,"art")
# 화면 쪽 배선(swMulti 포함)은 그대로 두었으므로 축만 넣으면 바로 뜬다.
MK_TRIO = {
    "뉴트럴": ("#e8d3c2", "#cfa392", "#c08878"),
    "웜 베이지": ("#eed3ac", "#d9a878", "#c08a55"),
    "피치": ("#f6d6c4", "#f0a98a", "#e08a6a"),
    "코랄": ("#f7d2c6", "#ee8a72", "#e2604a"),
    "오렌지": ("#f6cfae", "#ef8340", "#dd6420"),
    "골드": ("#f0dcb0", "#d4a94b", "#b58a2e"),
    "쿨 핑크": ("#f7dbe4", "#eda3bb", "#df7f9e"),
    "로지": ("#efc9cf", "#d4798c", "#c25a70"),
    "모브": ("#e2cbd4", "#a8798e", "#8d5e74"),
    "브라운": ("#e3c8b4", "#8f6249", "#74472f"),
    "레드": ("#f0cfc9", "#cf2f3c", "#a8121f"),
    "그레이·쿨": ("#dcdde1", "#9aa0a8", "#767d86"),
    "모노크롬": ("#d6d6d8", "#8a8a90", "#57585c"),
}
_BG_RECT = '<rect x="2" y="2" width="36" height="36" rx="9" fill="#f6f3ef"/>'


def swatches_json():
    """화면이 색 격자를 그리는 데 필요한 것만 담아서 넘긴다.

    선택지 이름은 건드리지 않는다. 화면에서 고르면 원래 있던 <select> 의
    값을 바꾸는 방식이라, 저장해 둔 모델·대화창 패치·되돌리기가 그대로 돈다.
    """
    out = {}
    for key, kind in SWATCH_KIND.items():
        items = {}
        for o in BY_KEY(key):
            if kind == "art":
                sv = icon(key, o)
                if not sv:
                    continue
                items[o] = {"svg": sv.replace(_BG_RECT, "", 1)
                            if key != "dye" else sv}
            elif kind == "trio":
                items[o] = {"trio": list(MK_TRIO[o])}
            elif kind == "under":
                items[o] = {"c": UNDERTONE[o], "base": "#e8d5c4"}
            else:
                items[o] = {"c": (SKIN if key == "skin" else HAIR)[o]}
        out[key] = {"kind": kind, "items": items}
    out["hair_color"]["groups"] = [[g, n] for g, n in HAIR_GROUPS]
    if "features" in out:                # 여러 개를 같이 켜는 칸이다
        out["features"]["multi"] = True
    return out


def BY_KEY(key):
    a = {x["key"]: x for _g, ax in mt.GROUPS for x in ax}[key]
    return [o for o in a["table"] if o != mt.NONE]


def coverage():
    """몇 개나 그려지는지 센다. 새 선택지를 넣고 여기가 줄면 빠진 것이다."""
    drawn = missing = textonly = 0
    holes = []
    for _g, axes in mt.GROUPS:
        for a in axes:
            tbl = a.get("table")
            if not tbl:
                continue
            for o in tbl:
                if o == mt.NONE:
                    continue
                if a["key"] in ICON_NONE:
                    textonly += 1
                elif icon(a["key"], o):
                    drawn += 1
                else:
                    missing += 1
                    holes.append("%s / %s" % (a["key"], o))
    return {"drawn": drawn, "textonly": textonly, "missing": missing, "holes": holes}


if __name__ == "__main__":
    c = coverage()
    print("그려짐 %d · 글자로 남김 %d · 빠짐 %d" % (c["drawn"], c["textonly"], c["missing"]))
    for h in c["holes"][:40]:
        print("   빠짐:", h)
