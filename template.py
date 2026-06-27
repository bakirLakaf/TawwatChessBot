# -*- coding: utf-8 -*-
"""
مولّد قالب منشورات صفحة "Tawwat Chess".
منشور مربّع 1080x1080:
- خلفية بنمط مختار (نجمة إسلامية / معيّنات / شطرنج مائل / سداسيات / سادة)
- شارة تصنيف ملوّنة + ترويسة
- منطقة محتوى: صورة خارجية أو رقعة شطرنج (قطع ألفا PNG)
- اللوغو أسفل اليسار + عنوان عربي عريض
العربية تُرسم عبر محرّك raqm المدمج في Pillow.
لا يحتاج cairo وقت التشغيل (القطع صور PNG جاهزة).
"""
import os, re, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
F_BOLD = os.path.join(ASSETS, "Tajawal-Bold.ttf")
F_XBOLD = os.path.join(ASSETS, "Tajawal-ExtraBold.ttf")
F_REG = os.path.join(ASSETS, "Tajawal-Regular.ttf")
LOGO = os.path.join(ASSETS, "logo_white.png")
KNIGHT = os.path.join(ASSETS, "knight_white.png")
PIECES_DIR = os.path.join(ASSETS, "pieces_alpha")   # قطع ألفا الجاهزة

GOLD = (201, 162, 75)
WHITE = (244, 240, 230)
MUTED = (154, 143, 121)
PANEL = (33, 29, 23)
SHADE = (18, 16, 13)

CATS = {
    "news":       {"label": "خبر",                  "color": (201, 162, 75)},
    "news_en":    {"label": "News",                 "color": (201, 162, 75)},
    "puzzle":     {"label": "لغز",                  "color": (46, 139, 111)},
    "classic":    {"label": "نقلة من الزمن الجميل", "color": (150, 110, 200)},
    "wisdom":     {"label": "حكمة شطرنجية",         "color": (74, 120, 176)},
    "tournament": {"label": "بطولة",                "color": (192, 70, 55)},
    "results":    {"label": "نتائج",                "color": (201, 162, 75)},
    "challenge":  {"label": "تحدّي الوضعية",        "color": (210, 140, 50)},
}

# ---------------- نص عربي (يعمل مع/بدون libraqm) ----------------
# مع libraqm (Linux/Railway غالبًا): نرسم مباشرة باتجاه RTL — أجمل نتيجة.
# بدون libraqm (ويندوز): نهيّئ النص يدويًا (وصل الحروف + ترتيب RTL)، ونصلح
# الأشكال المعزولة التي لا يملكها خط Tajawal بإعادتها للحرف الأساسي (نفس الشكل).
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import features as _pil_features

_HAS_RAQM = _pil_features.check("raqm")
AR_RE = re.compile(r"[\u0600-\u06FF]")

# شكل معزول مفقود في Tajawal -> الحرف الأساسي المطابق بصريًا
_ISO_FIX = {0xFE80:0x0621, 0xFE81:0x0622, 0xFE83:0x0623, 0xFE85:0x0624, 0xFE87:0x0625,
            0xFE89:0x0626, 0xFE8D:0x0627, 0xFE8F:0x0628, 0xFE93:0x0629, 0xFE95:0x062A,
            0xFE99:0x062B, 0xFE9D:0x062C, 0xFEA1:0x062D, 0xFEA5:0x062E, 0xFEA9:0x062F,
            0xFEAB:0x0630, 0xFEAD:0x0631, 0xFEAF:0x0632, 0xFEB1:0x0633, 0xFEB5:0x0634,
            0xFEB9:0x0635, 0xFEBD:0x0636, 0xFEC1:0x0637, 0xFEC5:0x0638, 0xFEC9:0x0639,
            0xFECD:0x063A, 0xFED1:0x0641, 0xFED5:0x0642, 0xFED9:0x0643, 0xFEDD:0x0644,
            0xFEE1:0x0645, 0xFEE5:0x0646, 0xFEE9:0x0647, 0xFEED:0x0648, 0xFEEF:0x0649,
            0xFEF1:0x064A}

def adir(t): return "rtl" if AR_RE.search(t) else "ltr"

def shape(t):
    """مسار بدون raqm: وصل الحروف + إصلاح المعزولة + ترتيب RTL.
    نُجبر الاتجاه الأساسي على RTL حتى لو بدأ النص بكلمة لاتينية (مثل اسم لاعب)،
    وإلا تعكس bidi ترتيب المقاطع (FIDE … Buettner بدل Buettner … FIDE)."""
    if not t or not AR_RE.search(t):
        return t
    reshaped = arabic_reshaper.reshape(t).translate(_ISO_FIX)
    try:
        return get_display(reshaped, base_dir="R")
    except TypeError:                 # توافق مع إصدارات python-bidi الأقدم
        return get_display(reshaped)

_fc = {}
def font(path, size):
    k = (path, size)
    if k not in _fc:
        eng = ImageFont.Layout.RAQM if _HAS_RAQM else ImageFont.Layout.BASIC
        _fc[k] = ImageFont.truetype(path, size, layout_engine=eng)
    return _fc[k]

def text_w(d, t, f):
    if _HAS_RAQM:
        return d.textlength(t, font=f, direction=adir(t))
    return d.textlength(shape(t), font=f)

def dtext(d, xy, t, f, anchor, fill, **kw):
    if _HAS_RAQM:
        d.text(xy, t, font=f, anchor=anchor, fill=fill, direction=adir(t), **kw)
    else:
        d.text(xy, shape(t), font=f, anchor=anchor, fill=fill, **kw)
def wrap_ar(d, text, f, max_w):
    words = text.split(); lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_w(d, trial, f) <= max_w or not cur: cur = trial
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# إزالة الإيموجي من النص المرسوم على الصورة (الخط لا يملك رموزها فتظهر مربّعات).
# الإيموجي يبقى في نص فيسبوك، ويُحذف فقط من الكتابة فوق الصورة.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE0F\U0000200D]+")
def strip_emoji(t):
    if not t:
        return t
    return re.sub(r"\s+", " ", _EMOJI.sub("", t)).strip()

# ---------------- أنماط الخلفية ----------------
def _base(w, h): return Image.new("RGB", (w, h), SHADE)
def bg_plain(w, h): return _base(w, h)
def bg_diamond(w, h):
    img = _base(w, h); d = ImageDraw.Draw(img); s = 60; ln = (37, 33, 26)
    for x in range(-h, w + h, s):
        d.line([(x, 0), (x + h, h)], fill=ln, width=2)
        d.line([(x, 0), (x - h, h)], fill=ln, width=2)
    return img
def bg_diag(w, h):
    s = 110; big = Image.new("RGB", (w*2, h*2), (20, 18, 14)); d = ImageDraw.Draw(big)
    for r in range((h*2)//s + 2):
        for c in range((w*2)//s + 2):
            if (r + c) % 2 == 0:
                d.rectangle([c*s, r*s, c*s+s, r*s+s], fill=(30, 27, 21))
    big = big.rotate(45, resample=Image.BICUBIC)
    l, t = (big.width - w)//2, (big.height - h)//2
    return big.crop((l, t, l + w, t + h))
def _hexpts(cx, cy, r):
    return [(cx + r*math.cos(math.radians(60*i - 30)),
             cy + r*math.sin(math.radians(60*i - 30))) for i in range(6)]
def bg_hex(w, h):
    img = _base(w, h); d = ImageDraw.Draw(img); r = 44; ln = (35, 31, 24)
    dx = r*math.sqrt(3); dy = r*1.5; row = 0; y = 0
    while y < h + r:
        x = (dx/2 if row % 2 else 0) - dx
        while x < w + dx:
            d.polygon(_hexpts(x, y, r), outline=ln, width=2); x += dx
        y += dy; row += 1
    return img
def bg_star(w, h):
    img = _base(w, h); d = ImageDraw.Draw(img); s = 110; ln = (40, 35, 27)
    half = s*0.46; dia = half*1.41
    for r in range(-1, h//s + 2):
        for c in range(-1, w//s + 2):
            cx, cy = c*s + s/2, r*s + s/2
            d.rectangle([cx-half, cy-half, cx+half, cy+half], outline=ln, width=2)
            d.polygon([(cx, cy-dia), (cx+dia, cy), (cx, cy+dia), (cx-dia, cy)],
                      outline=ln, width=2)
    return img
BACKGROUNDS = {"star": bg_star, "diamond": bg_diamond, "diag": bg_diag,
               "hex": bg_hex, "plain": bg_plain}

# ---------------- صور مساعدة ----------------
def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *img.size], radius=radius, fill=255)
    out = img.convert("RGBA"); out.putalpha(mask); return out
def cover(img, w, h):
    img = img.convert("RGB"); sr = img.width/img.height; dr = w/h
    if sr > dr: nw, nh = int(h*sr), h
    else: nw, nh = w, int(w/sr)
    img = img.resize((nw, nh), Image.LANCZOS)
    l, t = (nw-w)//2, (nh-h)//2
    return img.crop((l, t, l+w, t+h))

def fit_card(img, w, h):
    """يُظهر الصورة كاملةً (بلا قصّ) داخل إطار w×h، ويملأ الفراغ بخلفية
    مموّهة معتمة من الصورة نفسها (بلا أشرطة مسطّحة)."""
    img = img.convert("RGB")
    bg = cover(img, w, h).filter(ImageFilter.GaussianBlur(20))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    sr = img.width / img.height; dr = w / h
    if sr > dr:                       # أعرض من الإطار → عرض كامل
        nw, nh = w, max(1, round(w / sr))
    else:                             # أطول من الإطار → ارتفاع كامل
        nw, nh = max(1, round(h * sr)), h
    fitted = img.resize((nw, nh), Image.LANCZOS)
    bg.paste(fitted, ((w - nw) // 2, (h - nh) // 2))
    return bg

# ---------------- رقعة الشطرنج (قطع PNG) ----------------
LIGHT_SQ = (235, 214, 176); DARK_SQ = (181, 138, 86)
_pcache = {}
def piece_png(code, size):
    k = (code, size)
    if k not in _pcache:
        im = Image.open(os.path.join(PIECES_DIR, code + ".png")).convert("RGBA")
        _pcache[k] = im.resize((size, size), Image.LANCZOS)
    return _pcache[k]
def fen_code(ch): return ("w" if ch.isupper() else "b") + ch.upper()
def draw_board(fen, square=104, coords=True):
    margin = 30 if coords else 0; size = square*8; full = size + margin
    bd = Image.new("RGBA", (full, full), (28, 24, 19, 255)); d = ImageDraw.Draw(bd)
    ox = margin
    for r in range(8):
        for c in range(8):
            col = LIGHT_SQ if (r+c) % 2 == 0 else DARK_SQ
            d.rectangle([ox+c*square, r*square, ox+c*square+square, r*square+square], fill=col)
    rr = 0
    for rank in fen.split()[0].split("/"):
        cc = 0
        for ch in rank:
            if ch.isdigit(): cc += int(ch)
            else:
                bd.alpha_composite(piece_png(fen_code(ch), square), (ox+cc*square, rr*square))
                cc += 1
        rr += 1
    if coords:
        cf = font(F_REG, 22); files = "abcdefgh"
        for c in range(8):
            d.text((ox+c*square+square//2, full-margin//2), files[c], font=cf, anchor="mm", fill=MUTED)
        for r in range(8):
            d.text((margin//2, r*square+square//2), str(8-r), font=cf, anchor="mm", fill=MUTED)
    return bd

# ---------------- الإطار الرئيسي ----------------
W = H = 1080; HEADER_H = 152; BOTTOM_H = 196
def _pill_text_color(c):
    lum = 0.299*c[0] + 0.587*c[1] + 0.114*c[2]
    return (20, 18, 14) if lum > 150 else (255, 255, 255)

def create_post(category, header_label, title, subtitle="", content_image=None,
                fen=None, background="diag", output="output/post.png",
                pill_label=None, pill_color=None):
    cat = CATS.get(category, CATS["news"])
    label = strip_emoji(pill_label or cat["label"])
    pill_fill = pill_color or cat["color"]          # لون الشارة
    head_accent = pill_color or GOLD                 # لون الترويسة/الإطار (ذهبي افتراضيًا)
    header_label = strip_emoji(header_label); title = strip_emoji(title); subtitle = strip_emoji(subtitle)
    img = BACKGROUNDS.get(background, bg_diag)(W, H).convert("RGBA")
    d = ImageDraw.Draw(img)

    # الترويسة
    d.rectangle([0, 0, W, HEADER_H], fill=(20, 18, 14))
    d.line([0, HEADER_H, W, HEADER_H], fill=head_accent, width=3)
    # الشارة (يسار) باللون المميّز للموضوع
    pf = font(F_BOLD, 34); pw = text_w(d, label, pf)
    pill_w, pill_h = pw + 56, 60; px0, py0 = 45, (HEADER_H - pill_h)//2
    d.rounded_rectangle([px0, py0, px0+pill_w, py0+pill_h], radius=pill_h//2, fill=pill_fill)
    dtext(d, (px0+pill_w/2, py0+pill_h/2), label, pf, "mm", _pill_text_color(pill_fill))
    # ترويسة يمين (اسم الحدث/البطولة) مع تصغير تلقائي ليتّسع — يدعم RTL والـLTR
    avail = (W - 45) - (px0 + pill_w + 24)
    hsize = 46; hf = font(F_BOLD, hsize)
    while hsize > 22 and text_w(d, header_label, hf) > avail:
        hsize -= 2; hf = font(F_BOLD, hsize)
    dtext(d, (W-45, HEADER_H//2), header_label, hf, "rm", head_accent)

    # المحتوى
    c_top = HEADER_H + 34; c_bottom = H - BOTTOM_H - 22
    c_left, c_right = 50, W - 50; cw, chh = c_right - c_left, c_bottom - c_top
    if fen:
        board = draw_board(fen); scale = min(cw, chh)/board.width
        bw = int(board.width*scale); board = rounded(board.resize((bw, bw), Image.LANCZOS), 14)
        bx, by = c_left + (cw-bw)//2, c_top + (chh-bw)//2
        d.rounded_rectangle([bx-4, by-4, bx+bw+4, by+bw+4], radius=18, outline=GOLD, width=3)
        img.alpha_composite(board, (bx, by))
    elif content_image and os.path.exists(content_image):
        photo = rounded(fit_card(Image.open(content_image), cw, chh), 16)
        d.rounded_rectangle([c_left-3, c_top-3, c_right+3, c_bottom+3], radius=19, outline=head_accent, width=3)
        img.alpha_composite(photo, (c_left, c_top))
    else:
        d.rounded_rectangle([c_left, c_top, c_right, c_bottom], radius=16, fill=PANEL, outline=(70, 62, 50), width=2)
        kn = Image.open(KNIGHT).convert("RGBA"); kh = int(chh*0.5)
        kn = kn.resize((int(kn.width*kh/kn.height), kh), Image.LANCZOS)
        a = kn.split()[-1].point(lambda v: int(v*38/255)); kn.putalpha(a)
        img.alpha_composite(kn, (c_left + (cw-kn.width)//2, c_top + (chh-kn.height)//2 - 20))
        dtext(d, ((c_left+c_right)/2, c_bottom-50), "منطقة الصورة (تُسحب تلقائيًا)", font(F_REG, 30), "mm", MUTED)

    # الشريط السفلي
    d.line([45, H-BOTTOM_H, W-45, H-BOTTOM_H], fill=(70, 62, 50), width=2)
    logo = Image.open(LOGO).convert("RGBA"); lh = 128
    logo = logo.resize((int(logo.width*lh/logo.height), lh), Image.LANCZOS)
    img.alpha_composite(logo, (45, H-BOTTOM_H + (BOTTOM_H-lh)//2))
    title_left = 45 + logo.width + 36
    tf = font(F_XBOLD, 62); max_tw = (W-45) - title_left
    lines = wrap_ar(d, title, tf, max_tw)[:2]; line_h = 74
    sub_h = 40 if subtitle else 0
    total_h = line_h*len(lines) + sub_h
    top = (H - BOTTOM_H) + (BOTTOM_H - total_h)//2
    y0 = top + line_h//2
    for i, ln in enumerate(lines):
        dtext(d, (W-45, y0 + i*line_h), ln, tf, "rm", WHITE)
    if subtitle:
        dtext(d, (W-45, top + line_h*len(lines) + sub_h//2), subtitle, font(F_BOLD, 30), "rm", GOLD)

    out_path = os.path.join(BASE, output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, quality=95)
    return out_path

def create_text_card(category, header_label, headline, subline="", show_quote=True,
                     background="diag", footer_text="Tawwat Chess", output="output/card.png"):
    """بطاقة نصية (حكمة/إعلان): نص كبير في الوسط بنفس هوية الصفحة.
    headline: النص الكبير. subline: السطر الصغير تحته. show_quote: إظهار علامة الاقتباس."""
    cat = CATS.get(category, CATS["wisdom"])
    header_label = strip_emoji(header_label); headline = strip_emoji(headline); subline = strip_emoji(subline)
    img = BACKGROUNDS.get(background, bg_diag)(W, H).convert("RGBA")
    d = ImageDraw.Draw(img)

    # الترويسة (نفس نمط create_post)
    d.rectangle([0, 0, W, HEADER_H], fill=(20, 18, 14))
    d.line([0, HEADER_H, W, HEADER_H], fill=GOLD, width=3)
    dtext(d, (W-45, HEADER_H//2), header_label, font(F_BOLD, 46), "rm", GOLD)
    pf = font(F_BOLD, 34); pw = text_w(d, cat["label"], pf)
    pill_w, pill_h = pw + 56, 60; px0, py0 = 45, (HEADER_H - pill_h)//2
    d.rounded_rectangle([px0, py0, px0+pill_w, py0+pill_h], radius=pill_h//2, fill=cat["color"])
    dtext(d, (px0+pill_w/2, py0+pill_h/2), cat["label"], pf, "mm", _pill_text_color(cat["color"]))

    # اللوحة الوسطى
    c_top = HEADER_H + 34; c_bottom = H - BOTTOM_H - 22; c_left, c_right = 50, W - 50
    cw, chh = c_right - c_left, c_bottom - c_top
    d.rounded_rectangle([c_left, c_top, c_right, c_bottom], radius=18, fill=PANEL,
                        outline=(70, 62, 50), width=2)
    cx = (c_left + c_right) / 2
    head_top = c_top
    if show_quote:
        dtext(d, (cx, c_top + 92), "”", font(F_XBOLD, 150), "mm", cat["color"])
        head_top = c_top + 60

    # ملاءمة حجم الخط تلقائيًا
    size = 60; tf = font(F_XBOLD, size); lines = wrap_ar(d, headline, tf, cw - 130); lh = size + 16
    while size > 30 and len(lines) * lh > (c_bottom - head_top) - 150:
        size -= 4; tf = font(F_XBOLD, size); lines = wrap_ar(d, headline, tf, cw - 130); lh = size + 16
    lines = lines[:6]; block_h = len(lines) * lh
    y0 = head_top + ((c_bottom - head_top) - block_h)//2 + 14
    for i, ln in enumerate(lines):
        dtext(d, (cx, y0 + i*lh), ln, tf, "mm", WHITE)
    if subline:
        dtext(d, (cx, y0 + block_h + 30), subline, font(F_BOLD, 36), "mm", cat["color"])

    # الشريط السفلي: اللوغو + اسم الصفحة
    d.line([45, H-BOTTOM_H, W-45, H-BOTTOM_H], fill=(70, 62, 50), width=2)
    logo = Image.open(LOGO).convert("RGBA"); lh2 = 128
    logo = logo.resize((int(logo.width*lh2/logo.height), lh2), Image.LANCZOS)
    img.alpha_composite(logo, (45, H-BOTTOM_H + (BOTTOM_H-lh2)//2))
    if footer_text:
        dtext(d, (W-45, (H-BOTTOM_H) + BOTTOM_H//2), strip_emoji(footer_text), font(F_BOLD, 40), "rm", WHITE)

    out_path = os.path.join(BASE, output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, quality=95)
    return out_path


if __name__ == "__main__":
    create_post("puzzle", "لغز الأسبوع", "الأبيض يلعب ويربح",
                "مات في نقلة — الحل في أول تعليق",
                fen="6k1/5ppp/8/8/8/8/8/3Q2K1 w - - 0 1",
                background="star", output="output/final_puzzle.png")
    print("ok")
