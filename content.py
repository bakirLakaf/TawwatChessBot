# -*- coding: utf-8 -*-
"""
بناء بطاقات المحتوى المجدول (تعيد: مسار الصورة، نص المنشور، تعليق اختياري).
- الحكمة: من data/quotes.json
- نقلة الزمن الجميل: من data/classic_games.json (وضعيات مُتحقَّقة)
- اللغز: من Lichess (لغز اليوم)
- البطولة: إعلان أسبوعي بقالب جاهز
يتم التدوير عبر مؤشّرات في قاعدة البيانات لتجنّب التكرار.
"""
import os
import json
import uuid
import logging
import template
import database as db
import lichess_puzzle

log = logging.getLogger(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def _tok():
    return uuid.uuid4().hex[:10]


# ---------- حكمة شطرنجية ----------
def make_wisdom():
    quotes = _load("quotes.json")
    idx = int(db.get_state("wisdom_idx", "0")) % len(quotes)
    db.set_state("wisdom_idx", idx + 1)
    q = quotes[idx]
    img = template.create_text_card(
        "wisdom", "حكمة شطرنجية", q["q"], "— " + q["a"],
        show_quote=True, output=f"cards/wisdom_{_tok()}.jpg")
    caption = (f"♟️ حكمة شطرنجية\n\n«{q['q']}»\n— {q['a']}\n\n"
               f"#شطرنج #حكمة_شطرنجية #TawwatChess")
    return img, caption, None


# ---------- نقلة من الزمن الجميل ----------
def make_classic():
    games = _load("classic_games.json")
    idx = int(db.get_state("classic_idx", "0")) % len(games)
    db.set_state("classic_idx", idx + 1)
    g = games[idx]
    img = template.create_post(
        "classic", "نقلة من الزمن الجميل", g["name"],
        f"{g['players']} · {g['year']}", fen=g["fen"],
        output=f"cards/classic_{_tok()}.jpg")
    caption = (f"📜 نقلة من الزمن الجميل\n\n{g['story']}\n\n"
               f"♟️ {g['players']} — {g['event']} ({g['year']})\n\n"
               f"#شطرنج #تاريخ_الشطرنج #TawwatChess")
    return img, caption, None


# ---------- لغز (Lichess) ----------
_MIN_RATING = 1500          # نتجاهل الألغاز السهلة دائمًا
_HARD_RATING = 2100         # حدّ «صعب»


def _rating_ok(rating, difficulty):
    if rating is None:
        return difficulty is None          # لا نعرف التصنيف → نقبله فقط للعشوائي
    if rating < _MIN_RATING:
        return False                       # سهل → مرفوض دائمًا
    if difficulty == "medium":
        return rating < _HARD_RATING
    if difficulty == "hard":
        return rating >= _HARD_RATING
    return True                            # عشوائي (متوسط أو صعب)


def make_puzzle(difficulty=None):
    """difficulty: 'medium' أو 'hard' أو None (عشوائي متوسط/صعب). يتجنّب التكرار والسهل."""
    import time
    p = None
    for attempt in range(3):                # محاولات محدودة (تفادي حظر Lichess)
        if attempt:
            time.sleep(1.2)
        cand = lichess_puzzle.get_puzzle(difficulty)
        if not cand:
            continue
        if db.is_seen("puzzle:" + cand["id"]):
            continue
        if _rating_ok(cand.get("rating"), difficulty):
            p = cand
            break
        p = p or cand                       # احتفظ بآخر مرشّح كحلّ أخير
    if not p:                               # احتياط: لغز اليوم (نقطة نهاية مستقرّة)
        d = lichess_puzzle.get_daily_puzzle()
        if d and not db.is_seen("puzzle:" + d["id"]):
            p = d
    if not p:
        return None
    db.mark_seen("puzzle:" + p["id"], "puzzle")
    diff_label = "صعب" if (p.get("rating") or 0) >= _HARD_RATING else "متوسط"
    img = template.create_post(
        "puzzle", "لغز شطرنج", f"{p['turn']} يلعب ويربح",
        f"الحل في أول تعليق 👇 · {diff_label}", fen=p["fen"],
        output=f"cards/puzzle_{_tok()}.jpg")
    caption = (f"🧩 لغز شطرنج ({diff_label})\n\n{p['turn']} يلعب. ما أفضل نقلة؟ "
               f"ضع حلّك في التعليقات! 👇\n\n"
               f"#شطرنج #لغز_شطرنج #TawwatChess")
    comment = f"✅ الحل: {p['solution']}\n🔗 lichess.org/training/{p['id']}"
    return img, caption, comment


# ---------- إعلان البطولة (بتفاصيل من المستخدم) ----------
def make_tournament(details=None):
    """details: dict اختياري فيه name/when/system/link/prize. بدونه يستعمل قيمًا افتراضية."""
    d = details or {}
    name = d.get("name") or "البطولة الأسبوعية"
    when = d.get("when") or "الجمعة 21:00 (توقيت الجزائر)"
    system = d.get("system") or "أرينا 5+0"
    link = d.get("link") or ""
    prize = d.get("prize") or ""

    sub = f"{when} · {system}" if system else when
    img = template.create_text_card(
        "tournament", "بطولة", name, sub,
        show_quote=False, output=f"cards/tournament_{_tok()}.jpg")

    lines = [f"🏆 {name} على Lichess!", "", f"🗓️ {when}", f"⏱️ النظام: {system}"]
    if prize:
        lines.append(f"🏅 الجائزة: {prize}")
    if link:
        lines.append(f"🔗 رابط البطولة: {link}")
    lines += ["", "كونوا في الموعد 👇", "", "#شطرنج #بطولة #TawwatChess"]
    caption = "\n".join(lines)
    return img, caption, None
