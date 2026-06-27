# -*- coding: utf-8 -*-
"""
بوت Tawwat Chess — كامل (أخبار + ألغاز + حكم + نقلات الزمن الجميل + بطولة).

الأخبار: كل فترة يقرأ RSS → يصيغ بالعربية (Claude) → بطاقة بالقالب → موافقتك → فيسبوك.
المحتوى المجدول: في أوقات ثابتة (انظر config.SCHEDULE) يجهّز لغزًا/حكمة/نقلة/إعلان بطولة.
  - SCHEDULED_AUTO_PUBLISH=false → يُرسل لك للموافقة في وقته (آمن).
  - SCHEDULED_AUTO_PUBLISH=true  → نشر تلقائي هادئ في وقته.
أوامر يدوية للتجربة: /check /puzzle /wisdom /classic /tournament

التشغيل: python bot.py   (يحتاج .env معبّأً)
"""
import os
import uuid
import asyncio
import logging
import datetime
import threading
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, InputMediaPhoto, BotCommand)
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ContextTypes, filters)

import config
import database as db
import news_sources
import rewriter
import facebook_api
import template
import content
import notify
import players

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
# كتم سجلّات المكتبات المزعجة — والأهمّ: httpx يطبع رابط الطلب وفيه توكن البوت!
for _noisy in ("httpx", "httpcore", "apscheduler", "telegram.ext.Application"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("tawwat")

ADMIN = config.TELEGRAM_ADMIN_CHAT_ID
CARDS_DIR = "cards"


# ---------------- صفحة حالة (Railway) ----------------
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Tawwat Chess bot is running.".encode("utf-8"))

    def log_message(self, *a):
        pass


def start_health_server(port):
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), _Health)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("صفحة الحالة على المنفذ %s", port)
    except Exception as e:
        log.warning("تعذّر تشغيل صفحة الحالة: %s", e)


# ---------------- أدوات ----------------
def _is_admin(update):
    chat = update.effective_chat
    return chat is not None and str(chat.id) == str(ADMIN)


def _download_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            path = os.path.join(CARDS_DIR, f"src_{uuid.uuid4().hex[:8]}.jpg")
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except Exception as e:
        log.warning("تعذّر تنزيل الصورة: %s", e)
    return None


# هوية بصرية حسب موضوع الخبر: شارة ولون مميّزان، والخلفية ثابتة = شطرنج مائل (diag)
NEWS_THEMES = {
    "result":          {"ar": "نتائج",        "en": "Results",     "color": (201, 162, 75),  "bg": "diag"},
    "tournament":      {"ar": "بطولة",        "en": "Tournament",  "color": (192, 70, 55),   "bg": "diag"},
    "historical":      {"ar": "ذكريات",       "en": "Memories",    "color": (150, 110, 200), "bg": "diag"},
    "interview":       {"ar": "حوار",         "en": "Interview",   "color": (74, 120, 176),  "bg": "diag"},
    "statement":       {"ar": "تصريح",        "en": "Statement",   "color": (60, 150, 150),  "bg": "diag"},
    "obituary":        {"ar": "تأبين",        "en": "In Memoriam", "color": (130, 130, 130), "bg": "diag"},
    "opening":         {"ar": "افتتاح",       "en": "Opening",     "color": (46, 139, 111),  "bg": "diag"},
    "arab_achievement": {"ar": "إنجاز عربي",  "en": "Arab Win",    "color": (46, 160, 100),  "bg": "diag"},
    "arab_general":    {"ar": "أخبار عربية",  "en": "Arab News",   "color": (201, 162, 75),  "bg": "diag"},
    "world_general":   {"ar": "أخبار عالمية", "en": "World News",  "color": (201, 162, 75),  "bg": "diag"},
}


def _resolve_category(category, is_arab):
    """يحوّل تصنيف النموذج إلى الهوية النهائية (يراعي اللاعبين العرب)."""
    if is_arab and category in ("result", "tournament"):
        return "arab_achievement"
    if category in ("general", "", None):
        return "arab_general" if is_arab else "world_general"
    return category if category in NEWS_THEMES else ("arab_general" if is_arab else "world_general")


def _make_news_card(data, local_img, token, lang="ar"):
    """يبني بطاقة خبر بلغة محدّدة من صورة مُنزّلة مسبقًا (تُشارَك بين النسختين).
    الترويسة = اسم الحدث، والشارة/اللون/الخلفية حسب تصنيف الخبر."""
    theme = NEWS_THEMES.get(data.get("category"), NEWS_THEMES["world_general"])
    header = (data.get("event") or "").strip() or ("أخبار الشطرنج" if lang == "ar" else "Chess News")
    cat = "news" if lang == "ar" else "news_en"
    return template.create_post(
        category=cat, header_label=header,
        title=data["title"], subtitle="", content_image=local_img,
        background=theme["bg"], pill_label=theme["ar" if lang == "ar" else "en"],
        pill_color=theme["color"],
        output=os.path.join(CARDS_DIR, f"{token}.jpg"))


def _keyboard(token):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نشر", callback_data=f"pub:{token}"),
         InlineKeyboardButton("✏️ تعديل", callback_data=f"edit:{token}")],
        [InlineKeyboardButton("💬 تعليق أول", callback_data=f"cmt:{token}"),
         InlineKeyboardButton("🗑️ حذف", callback_data=f"del:{token}")],
    ])


def _news_keyboard(token, lang="ar", has_alt=True):
    """لوحة أزرار الأخبار: نشر + تبديل اللغة + تعديل نص/صورة + تعليق أول + حذف."""
    top = [InlineKeyboardButton("✅ نشر", callback_data=f"pub:{token}")]
    if has_alt:
        other = "🇬🇧 English" if lang == "ar" else "🇸🇦 العربية"
        top.append(InlineKeyboardButton(other, callback_data=f"lang:{token}"))
    return InlineKeyboardMarkup([top,
        [InlineKeyboardButton("✏️ تعديل النص", callback_data=f"edit:{token}"),
         InlineKeyboardButton("🖼️ الصورة", callback_data=f"img:{token}")],
        [InlineKeyboardButton("💬 تعليق أول", callback_data=f"cmt:{token}"),
         InlineKeyboardButton("🗑️ حذف", callback_data=f"del:{token}")],
    ])


def _preview(caption):
    return caption if len(caption) <= 1000 else caption[:1000] + " …"


async def _send_for_approval(bot, token, image_path, caption):
    with open(image_path, "rb") as f:
        await bot.send_photo(chat_id=ADMIN, photo=f, caption=_preview(caption),
                             reply_markup=_keyboard(token))


async def _send_news_for_approval(bot, token, image_path, caption, lang="ar",
                                  has_alt=True, note=""):
    with open(image_path, "rb") as f:
        await bot.send_photo(chat_id=ADMIN, photo=f, caption=note + _preview(caption),
                             reply_markup=_news_keyboard(token, lang, has_alt))


def _in_post_window():
    """هل نحن ضمن نافذة النشر التلقائي (بتوقيت الجزائر)؟"""
    h = datetime.datetime.now(ZoneInfo(config.TIMEZONE)).hour
    return config.POST_WINDOW_START <= h < config.POST_WINDOW_END


def _fmt_date(epoch):
    """تاريخ الخبر بصيغة مقروءة بتوقيت الجزائر، أو '' إن غاب."""
    if not epoch:
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(epoch, ZoneInfo(config.TIMEZONE))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _card_title(caption):
    """عنوان البطاقة = أول سطر/مقطع من نص المنشور."""
    return (caption or "").split("\n\n")[0].split("\n")[0].strip()[:120] or "أخبار الشطرنج"


def _regen_news_images(token, src_path):
    """يعيد توليد بطاقة الخبر (والنسخة البديلة) بصورة جديدة مع الحفاظ على الهوية."""
    p = db.get_pending(token)
    lang = p.get("lang") or "ar"
    meta = {"event": p.get("event") or "", "category": p.get("category") or "general"}
    tag = uuid.uuid4().hex[:6]
    new_cur = _make_news_card({**meta, "title": _card_title(p["caption"])}, src_path,
                              f"{token}_img{tag}", lang)
    new_alt = None
    if p.get("alt_caption"):
        alt_lang = "en" if lang == "ar" else "ar"
        new_alt = _make_news_card({**meta, "title": _card_title(p["alt_caption"])}, src_path,
                                  f"{token}_img{tag}_alt", alt_lang)
    db.set_images(token, new_cur, new_alt)
    return new_cur


def _do_publish(image_path, caption, comment):
    """نشر متزامن (يُستدعى داخل to_thread). ينشر الصورة ثم يضيف الحل كتعليق إن وُجد."""
    ok, info = facebook_api.publish_photo(image_path, caption)
    if ok and comment:
        facebook_api.add_comment(info, comment)
    return ok, info


async def deliver(context, image_path, caption, comment=None, auto=False, label=""):
    """يضيف المنشور لقائمة الانتظار ثم: ينشر تلقائيًا أو يرسله لك للموافقة."""
    token = uuid.uuid4().hex[:12]
    db.add_pending(token, image_path, caption, "", comment)
    if auto:
        ok, info = await asyncio.to_thread(_do_publish, image_path, caption, comment)
        db.set_status(token, "published" if ok else "failed")
        await context.bot.send_message(
            ADMIN, f"✅ نُشر تلقائيًا ({label})." if ok else f"❌ فشل النشر ({label}): {info}")
    else:
        try:
            await _send_for_approval(context.bot, token, image_path, caption)
        except Exception as e:
            log.warning("تعذّر الإرسال على تيليجرام: %s", e)


async def deliver_news(context, token, ar, en, auto=False, event=None, category=None,
                       breaking=False, published=None):
    """خبر ثنائي اللغة: يخزّن النسختين ويرسل رسالة موافقة واحدة فيها زر تبديل اللغة.
    ينشر تلقائيًا فقط ضمن نافذة النشر — إلا إن كان عاجلًا فيُنشَر فورًا."""
    img_ar, cap_ar = ar
    if en:
        img_en, cap_en = en
        db.add_pending(token, img_ar, cap_ar, "", None,
                       alt_image_path=img_en, alt_caption=cap_en, lang="ar",
                       event=event, category=category)
    else:
        db.add_pending(token, img_ar, cap_ar, "", None, lang="ar",
                       event=event, category=category)
    # النشر التلقائي يعتمد العربية، ويُقيَّد بنافذة النشر إلا للأخبار العاجلة
    if auto and (breaking or _in_post_window()):
        ok, info = await asyncio.to_thread(_do_publish, img_ar, cap_ar, None)
        db.set_status(token, "published" if ok else "failed")
        await context.bot.send_message(
            ADMIN, "✅ نُشر تلقائيًا (خبر)." if ok else f"❌ فشل النشر (خبر): {info}")
        return
    # سطر معلومات يراه المشرف فقط (التاريخ + عاجل) — لا يدخل نصّ المنشور
    info_parts = []
    if breaking:
        info_parts.append("🔴 عاجل")
    d = _fmt_date(published)
    if d:
        info_parts.append("🗓️ " + d)
    note = (" · ".join(info_parts) + "\n\n") if info_parts else ""
    try:
        await _send_news_for_approval(context.bot, token, img_ar, cap_ar, "ar",
                                      has_alt=bool(en), note=note)
    except Exception as e:
        log.warning("تعذّر الإرسال على تيليجرام: %s", e)


# ---------------- مهمة الأخبار ----------------
async def _process_article(context, art):
    """يصوغ خبرًا (عربي + إنجليزي)، يبني البطاقتين، ويرسله للموافقة/النشر.
    يعيد True إن نجح. يُعلّم الخبر مرئيًا حتى لا يتكرّر تلقائيًا."""
    try:
        data_ar = await asyncio.to_thread(rewriter.to_arabic, art)
    except Exception as e:
        log.warning("فشل صياغة '%s': %s", art["title"][:40], e)
        return False
    data_en = None
    try:
        data_en = await asyncio.to_thread(rewriter.to_english, art)
    except Exception as e:
        log.warning("فشل النسخة الإنجليزية لـ '%s': %s", art["title"][:40], e)

    final_cat = _resolve_category(data_ar.get("category"), bool(art.get("arab_hits")))
    data_ar["category"] = final_cat
    if data_en:
        data_en["category"] = final_cat

    token = uuid.uuid4().hex[:12]
    src_img = await asyncio.to_thread(_download_image, art.get("image"))
    try:
        card_ar = await asyncio.to_thread(_make_news_card, data_ar, src_img, token, "ar")
    except Exception as e:
        log.warning("فشل توليد البطاقة: %s", e)
        return False
    cap_ar = rewriter.build_caption(art, data_ar, "ar")

    en_pack = None
    if data_en:
        try:
            card_en = await asyncio.to_thread(_make_news_card, data_en, src_img, token + "_en", "en")
            en_pack = (card_en, rewriter.build_caption(art, data_en, "en"))
        except Exception as e:
            log.warning("فشل البطاقة الإنجليزية: %s", e)

    db.mark_seen(art["hash"], art["title"])
    await deliver_news(context, token, (card_ar, cap_ar), en_pack,
                       auto=config.AUTO_PUBLISH, event=data_ar.get("event"),
                       category=final_cat, breaking=bool(art.get("breaking")),
                       published=art.get("published"))
    return True


async def check_news_job(context: ContextTypes.DEFAULT_TYPE, force=False, announce_empty=False):
    """الفحص الدوري/اليدوي: يلتقط الأخبار الجديدة فقط (يمنع التكرار)."""
    if not force and db.get_state("news_paused", "0") == "1":
        log.info("فحص الأخبار متوقّف مؤقتًا (من لوحة التحكم).")
        return
    log.info("فحص الأخبار…")
    try:
        articles = await asyncio.to_thread(news_sources.fetch_new, config.MAX_POSTS_PER_CHECK)
    except Exception as e:
        log.warning("فشل جلب الأخبار: %s", e)
        if announce_empty:
            await context.bot.send_message(ADMIN, "تعذّر جلب الأخبار الآن.")
        return
    if not articles:
        log.info("لا أخبار جديدة.")
        if announce_empty:
            await context.bot.send_message(
                ADMIN, "📭 لا أخبار جديدة حاليًا (كلها سبق التقاطها). "
                       "لإنشاء منشور خبر فورًا استعمل: 📝 إنشاء منشور ← 📰 خبر الآن.")
        return
    for art in articles:
        await _process_article(context, art)
    log.info("انتهى فحص الأخبار.")


async def _post_latest_news(context):
    """عند الطلب (زر «خبر الآن»): أحدث خبر مناسب حتى لو سبق نشره."""
    try:
        articles = await asyncio.to_thread(news_sources.fetch_new, 5, True)  # ignore_seen
    except Exception as e:
        log.warning("فشل جلب الأخبار: %s", e)
        await context.bot.send_message(ADMIN, "تعذّر جلب الأخبار الآن.")
        return
    if not articles:
        await context.bot.send_message(ADMIN, "تعذّر إيجاد خبر مناسب الآن (قد تكون المصادر متعذّرة).")
        return
    # فضّل خبرًا لم يُنشَر بعد؛ وإلا خذ الأحدث
    art = next((a for a in articles if not db.is_seen(a["hash"])), articles[0])
    if not await _process_article(context, art):
        await context.bot.send_message(ADMIN, "تعذّر تجهيز الخبر (مشكلة في الصياغة). جرّب مجددًا.")


# ---------------- تنظيف البطاقات القديمة (منع امتلاء القرص) ----------------
def _cleanup_cards(days=7):
    import time
    cutoff = time.time() - days * 86400
    removed = 0
    try:
        for fn in os.listdir(CARDS_DIR):
            fp = os.path.join(CARDS_DIR, fn)
            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                try:
                    os.remove(fp); removed += 1
                except OSError:
                    pass
    except Exception as e:
        log.info("تنظيف البطاقات: %s", e)
    if removed:
        log.info("نُظّفت %d بطاقة قديمة.", removed)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(_cleanup_cards, 7)


# ---------------- المحتوى المجدول ----------------
def _build_content(ctype):
    if ctype == "puzzle":
        return content.make_puzzle()
    if ctype == "wisdom":
        return content.make_wisdom()
    if ctype == "classic":
        return content.make_classic()
    if ctype == "tournament":
        return content.make_tournament()
    return None


async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    ctype = context.job.data
    log.info("محتوى مجدول: %s", ctype)
    # البطولة تحتاج تفاصيل منك → نذكّرك بدل النشر التلقائي
    if ctype == "tournament":
        await context.bot.send_message(
            ADMIN, "🏆 حان وقت إعلان البطولة الأسبوعية!\n"
                   "أرسل /tournament لإدخال تفاصيلها (الرابط، الوقت، النظام...).")
        return
    res = await asyncio.to_thread(_build_content, ctype)
    if not res:
        await context.bot.send_message(ADMIN, f"تعذّر تجهيز محتوى ({ctype}) الآن.")
        return
    img, caption, comment = res
    # نشر تلقائي فقط ضمن نافذة النشر؛ خارجها يُرسَل للموافقة
    auto = config.SCHEDULED_AUTO_PUBLISH and _in_post_window()
    await deliver(context, img, caption, comment, auto=auto, label=ctype)


# ---------------- القوائم التفاعلية (inline) ----------------
def _main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 إنشاء منشور", callback_data="menu:create")],
        [InlineKeyboardButton("📅 الجدولة", callback_data="menu:schedule"),
         InlineKeyboardButton("⚙️ التحكم", callback_data="menu:control")],
        [InlineKeyboardButton("📰 فحص الأخبار الآن", callback_data="menu:checknews")],
    ])


def _create_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ منشور يدوي", callback_data="manual:start")],
        [InlineKeyboardButton("📰 خبر الآن", callback_data="gen:news")],
        [InlineKeyboardButton("🧩 لغز", callback_data="gen:puzzle"),
         InlineKeyboardButton("💡 حكمة", callback_data="gen:wisdom")],
        [InlineKeyboardButton("📜 نقلة", callback_data="gen:classic"),
         InlineKeyboardButton("🏆 بطولة", callback_data="gen:tournament")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="menu:main")],
    ])


def _puzzle_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟡 متوسط", callback_data="pz:medium"),
         InlineKeyboardButton("🔴 صعب", callback_data="pz:hard")],
        [InlineKeyboardButton("🎲 عشوائي", callback_data="pz:random")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="menu:create")],
    ])


def _back_main_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="menu:main")]])


_DAYS_AR = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
_TYPE_AR = {"puzzle": "🧩 لغز", "wisdom": "💡 حكمة", "classic": "📜 نقلة",
            "tournament": "🏆 بطولة", "news": "📰 أخبار"}


def _schedule_text():
    lines = ["📅 الجدول الأسبوعي (توقيت الجزائر):", ""]
    for it in sorted(config.SCHEDULE, key=lambda x: (min(x["days"]), x["hour"])):
        days = "، ".join(_DAYS_AR[d] for d in it["days"])
        lines.append(f"• {_TYPE_AR.get(it['type'], it['type'])} — {days} {it['hour']:02d}:{it['minute']:02d}")
    lines += ["",
              f"🔎 فحص الأخبار: كل {int(config.NEWS_CHECK_MINUTES)} دقيقة",
              f"🕗 نافذة النشر التلقائي: {config.POST_WINDOW_START:02d}:00–{config.POST_WINDOW_END:02d}:00",
              "🔴 الأخبار العاجلة تُنشَر فورًا خارج النافذة.",
              "", "(لتعديل المواعيد: SCHEDULE في config.py)"]
    return "\n".join(lines)


async def _gen_content(context, ctype, difficulty=None):
    """يولّد محتوى من نوع محدّد ويرسله للموافقة (للأزرار التفاعلية)."""
    if ctype == "news":
        await _post_latest_news(context)     # عند الطلب: أحدث خبر فورًا
        return
    if ctype == "puzzle":
        res = await asyncio.to_thread(content.make_puzzle, difficulty)
    else:
        res = await asyncio.to_thread(_build_content, ctype)
    if not res:
        await context.bot.send_message(ADMIN, "تعذّر التجهيز الآن (قد يكون المصدر غير متاح).")
        return
    img, caption, comment = res
    await deliver(context, img, caption, comment, auto=False, label=ctype)


async def _post_manual(context, text, src_img):
    """منشور يدوي: يعيد صياغة نصّ المستخدم باحترافية ويبني بطاقة بصورته."""
    try:
        data = await asyncio.to_thread(rewriter.rewrite_manual, text)
    except Exception as e:
        log.warning("فشل صياغة المنشور اليدوي: %s", e)
        await context.bot.send_message(ADMIN, "تعذّرت صياغة النص (مشكلة في محرّك الصياغة). جرّب مجددًا.")
        return
    world, arab = players.classify(text + " " + (data.get("body") or ""))
    final_cat = _resolve_category(data.get("category"), bool(arab))
    data["category"] = final_cat
    token = uuid.uuid4().hex[:12]
    try:
        card = await asyncio.to_thread(_make_news_card, data, src_img, token, "ar")
    except Exception as e:
        log.warning("فشل بطاقة المنشور اليدوي: %s", e)
        await context.bot.send_message(ADMIN, "تعذّر توليد البطاقة. جرّب صورة أخرى.")
        return
    art = {"source": "", "arab_hits": arab, "world_hits": world}
    caption = rewriter.build_caption(art, data, "ar")
    await deliver_news(context, token, (card, caption), None, auto=False,
                       event=data.get("event"), category=final_cat)


# ---------------- لوحة التحكم ----------------
def _control_keyboard():
    paused = db.get_state("news_paused", "0") == "1"
    news_btn = "▶️ تشغيل الأخبار" if paused else "⏸️ إيقاف الأخبار"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(news_btn, callback_data="ctl:news")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="ctl:stats"),
         InlineKeyboardButton("🔄 تحديث القوائم", callback_data="ctl:reload")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="menu:main")],
    ])


def _stats_text():
    s = db.stats(); bs = s["by_status"]
    paused = db.get_state("news_paused", "0") == "1"
    return ("📊 إحصاءات:\n"
            f"• حالة الأخبار: {'موقوفة ⏸️' if paused else 'تعمل ▶️'}\n"
            f"• أخبار ملتقطة: {s['seen']}\n"
            f"• منشورة: {bs.get('published', 0)}\n"
            f"• بانتظار: {bs.get('pending', 0)}\n"
            f"• محذوفة: {bs.get('discarded', 0)}\n"
            f"• فشلت: {bs.get('failed', 0)}")


# ---------------- الأزرار ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(update):
        return
    try:
        action, token = q.data.split(":", 1)
    except ValueError:
        return

    # أزرار لوحة التحكم (لا تحتاج منشورًا معلّقًا)
    if action == "ctl":
        if token == "news":
            cur = db.get_state("news_paused", "0")
            db.set_state("news_paused", "0" if cur == "1" else "1")
            paused = db.get_state("news_paused", "0") == "1"
            await q.edit_message_text(
                "⏸️ تمّ إيقاف الأخبار التلقائية." if paused else "▶️ تمّ تشغيل الأخبار التلقائية.",
                reply_markup=_control_keyboard())
        elif token == "stats":
            await q.edit_message_text(_stats_text(), reply_markup=_control_keyboard())
        elif token == "reload":
            w, a = players.reload_lists()
            await q.edit_message_text(
                f"🔄 أُعيد تحميل القوائم: {w} لاعبًا عالميًا، {a} لاعبًا عربيًا.",
                reply_markup=_control_keyboard())
        return

    # القوائم التفاعلية
    if action == "menu":
        if token == "main":
            await q.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=_main_menu())
        elif token == "create":
            await q.edit_message_text("📝 اختر نوع المنشور:", reply_markup=_create_menu())
        elif token == "schedule":
            await q.edit_message_text(_schedule_text(), reply_markup=_back_main_kb())
        elif token == "control":
            await q.edit_message_text("⚙️ لوحة التحكم:", reply_markup=_control_keyboard())
        elif token == "checknews":
            await q.edit_message_text("📰 جارٍ فحص الأخبار…", reply_markup=_back_main_kb())
            await check_news_job(context, force=True, announce_empty=True)
        return

    # إنشاء منشور من تصنيف
    if action == "gen":
        if token == "puzzle":
            await q.edit_message_text("🧩 اختر مستوى اللغز:", reply_markup=_puzzle_menu())
            return
        if token == "tournament":
            context.bot_data["awaiting_tournament"] = True
            await q.edit_message_text("🏆 إدخال تفاصيل البطولة…")
            await context.bot.send_message(ADMIN, TOURNAMENT_FORM)
            return
        labels = {"news": "خبر", "wisdom": "حكمة", "classic": "نقلة"}
        await q.edit_message_text(f"⏳ جارٍ تجهيز ({labels.get(token, token)})…")
        await _gen_content(context, token)
        return

    # مستوى اللغز
    if action == "pz":
        diff = None if token == "random" else token
        await q.edit_message_text(f"⏳ جارٍ تجهيز لغز ({token})…")
        await _gen_content(context, "puzzle", difficulty=diff)
        return

    # بدء المنشور اليدوي
    if action == "manual":
        context.bot_data["awaiting_manual"] = "text"
        context.bot_data["manual_text"] = None
        await q.edit_message_text("✍️ أرسل نصّ المنشور، وسأعيد صياغته باحترافية بأسلوب الصفحة.")
        return

    # بقية الأزرار تخصّ منشورًا معلّقًا
    p = db.get_pending(token)
    if not p:
        await q.edit_message_caption("انتهت صلاحية هذا المنشور.")
        return
    base = q.message.caption or ""
    if action == "pub":
        await q.edit_message_caption(base + "\n\n⏳ جارٍ النشر…")
        ok, info = await asyncio.to_thread(_do_publish, p["image_path"], p["caption"], p.get("comment"))
        db.set_status(token, "published" if ok else "failed")
        await q.edit_message_caption(base + ("\n\n✅ تم النشر على فيسبوك" if ok else f"\n\n❌ فشل: {info}"))
        if ok:  # رابط المنشور لمشاركته يدويًا في مجموعاتك (فيسبوك لا يتيح النشر الآلي للمجموعات)
            link = f"https://www.facebook.com/{info}"
            await context.bot.send_message(
                ADMIN, f"🔗 رابط المنشور — شاركه في مجموعاتك:\n{link}",
                disable_web_page_preview=False)
    elif action == "del":
        db.set_status(token, "discarded")
        await q.edit_message_caption(base + "\n\n🗑️ تم الحذف.")
    elif action == "cmt":
        context.bot_data["awaiting_comment"] = token
        cur = p.get("comment")
        hint = f"\n\n(التعليق الحالي: {cur})" if cur else ""
        await context.bot.send_message(
            ADMIN, "💬 أرسل الآن نص التعليق الأول (يُنشَر تحت المنشور تلقائيًا)."
                   " أرسل «حذف» لإزالته." + hint)
    elif action == "lang":
        new_lang = db.swap_pending_lang(token)
        if not new_lang:
            return
        p = db.get_pending(token)
        with open(p["image_path"], "rb") as f:
            await q.edit_message_media(
                InputMediaPhoto(media=f, caption=_preview(p["caption"])),
                reply_markup=_news_keyboard(token, new_lang, has_alt=True))
    elif action == "edit":
        context.bot_data["awaiting_edit"] = token
        await context.bot.send_message(ADMIN, "أرسل الآن نص المنشور الجديد كاملًا (سيستبدل النص الحالي).")
    elif action == "img":
        context.bot_data["awaiting_image"] = token
        await context.bot.send_message(
            ADMIN, "🖼️ أرسل الآن الصورة الجديدة (كصورة)، أو رابطًا مباشرًا لها يبدأ بـ http.")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال صورة: للمنشور اليدوي، أو لتعديل صورة منشور خبر."""
    if not _is_admin(update) or not update.message.photo:
        return
    # صورة المنشور اليدوي
    if context.bot_data.get("awaiting_manual") == "image":
        context.bot_data["awaiting_manual"] = None
        body = context.bot_data.get("manual_text") or ""
        src = os.path.join(CARDS_DIR, f"up_{uuid.uuid4().hex[:8]}.jpg")
        tgfile = await context.bot.get_file(update.message.photo[-1].file_id)
        await tgfile.download_to_drive(src)
        await update.message.reply_text("جارٍ تجهيز المنشور…")
        await _post_manual(context, body, src)
        return
    token = context.bot_data.get("awaiting_image")
    if not token:
        return
    context.bot_data["awaiting_image"] = None
    p = db.get_pending(token)
    if not p:
        await update.message.reply_text("انتهت صلاحية هذا المنشور.")
        return
    src = os.path.join(CARDS_DIR, f"up_{uuid.uuid4().hex[:8]}.jpg")
    tgfile = await context.bot.get_file(update.message.photo[-1].file_id)
    await tgfile.download_to_drive(src)
    await update.message.reply_text("جارٍ تحديث الصورة…")
    new_card = await asyncio.to_thread(_regen_news_images, token, src)
    p = db.get_pending(token)
    await _send_news_for_approval(context.bot, token, new_card, p["caption"],
                                  p.get("lang") or "ar", has_alt=bool(p.get("alt_caption")))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    text = (update.message.text or "").strip()
    # أزرار القائمة لها الأولوية
    if text in MENU_ACTIONS:
        context.bot_data["awaiting_edit"] = None
        context.bot_data["awaiting_tournament"] = False
        context.bot_data["awaiting_image"] = None
        context.bot_data["awaiting_comment"] = None
        context.bot_data["awaiting_manual"] = None
        await MENU_ACTIONS[text](update, context)
        return
    # تدفّق المنشور اليدوي
    manual = context.bot_data.get("awaiting_manual")
    if manual == "text":
        context.bot_data["manual_text"] = text
        context.bot_data["awaiting_manual"] = "image"
        await update.message.reply_text(
            "📷 أرسل الآن الصورة التي تريدها للمنشور، أو أرسل «بدون» لمنشور بلا صورة.")
        return
    if manual == "image":
        context.bot_data["awaiting_manual"] = None
        body = context.bot_data.get("manual_text") or text
        if text not in ("بدون", "بدونها", "-", "skip"):
            await update.message.reply_text("أرسل صورة، أو «بدون». سأكمل بلا صورة الآن.")
        await update.message.reply_text("جارٍ تجهيز المنشور…")
        await _post_manual(context, body, None)
        return
    # تدفّق ضبط التعليق الأول
    cmt_token = context.bot_data.get("awaiting_comment")
    if cmt_token:
        context.bot_data["awaiting_comment"] = None
        p = db.get_pending(cmt_token)
        if not p:
            await update.message.reply_text("انتهت صلاحية هذا المنشور.")
            return
        new_comment = None if text in ("حذف", "delete", "-") else text
        db.set_comment(cmt_token, new_comment)
        await update.message.reply_text(
            "تم حذف التعليق الأول." if new_comment is None
            else "تم ضبط التعليق الأول ✅ (سيُنشَر تلقائيًا تحت المنشور).")
        return
    # تدفّق تعديل صورة المنشور برابط
    img_token = context.bot_data.get("awaiting_image")
    if img_token:
        context.bot_data["awaiting_image"] = None
        if not text.startswith("http"):
            await update.message.reply_text("أرسل صورة مباشرة، أو رابطًا يبدأ بـ http.")
            return
        src = await asyncio.to_thread(_download_image, text)
        if not src:
            await update.message.reply_text("تعذّر تنزيل الصورة من الرابط. حاول مجددًا.")
            return
        if not db.get_pending(img_token):
            await update.message.reply_text("انتهت صلاحية هذا المنشور.")
            return
        await update.message.reply_text("جارٍ تحديث الصورة…")
        new_card = await asyncio.to_thread(_regen_news_images, img_token, src)
        p = db.get_pending(img_token)
        await _send_news_for_approval(context.bot, img_token, new_card, p["caption"],
                                      p.get("lang") or "ar", has_alt=bool(p.get("alt_caption")))
        return
    # تدفّق إدخال تفاصيل البطولة
    if context.bot_data.get("awaiting_tournament"):
        context.bot_data["awaiting_tournament"] = False
        details = None if text == "افتراضي" else _parse_tournament(text)
        await update.message.reply_text("جارٍ تجهيز إعلان البطولة…")
        img, caption, comment = await asyncio.to_thread(content.make_tournament, details)
        await deliver(context, img, caption, comment, auto=False, label="إعلان البطولة")
        return
    # تدفّق تعديل نص منشور
    token = context.bot_data.get("awaiting_edit")
    if not token:
        return
    new_caption = update.message.text
    db.set_caption(token, new_caption)
    context.bot_data["awaiting_edit"] = None
    p = db.get_pending(token)
    if not p:
        await update.message.reply_text("انتهت صلاحية هذا المنشور.")
        return
    await update.message.reply_text("تم تحديث النص. هذه المعاينة الجديدة:")
    if p.get("alt_caption"):  # خبر ثنائي اللغة → نُبقي زر تبديل اللغة
        await _send_news_for_approval(context.bot, token, p["image_path"], new_caption,
                                      p.get("lang") or "ar", has_alt=True)
    else:
        await _send_for_approval(context.bot, token, p["image_path"], new_caption)


# ---------------- إدخال تفاصيل البطولة ----------------
TOURNAMENT_FORM = (
    "📝 أرسل تفاصيل البطولة بهذا الشكل (انسخ السطور وعدّل القيم):\n\n"
    "الاسم: البطولة الأسبوعية\n"
    "اليوم والوقت: الجمعة 21:00 (توقيت الجزائر)\n"
    "النظام: أرينا 5+0\n"
    "الرابط: https://lichess.org/tournament/\n"
    "الجائزة: لقب الأسبوع\n\n"
    "أو أرسل كلمة: افتراضي"
)
_TFIELDS = {"الاسم": "name", "اليوم والوقت": "when", "اليوم": "when", "الوقت": "when",
            "النظام": "system", "الرابط": "link", "الجائزة": "prize"}


def _parse_tournament(text):
    d = {}
    for line in text.splitlines():
        sep = ":" if ":" in line else ("：" if "：" in line else None)
        if not sep:
            continue
        k, v = line.split(sep, 1)
        key = _TFIELDS.get(k.strip())
        if key and v.strip():
            d[key] = v.strip()
    return d


async def cmd_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    context.bot_data["awaiting_tournament"] = True
    await update.message.reply_text(TOURNAMENT_FORM)


# ---------------- أوامر ----------------
# لوحة الأزرار الدائمة أسفل المحادثة
MENU = ReplyKeyboardMarkup(
    [["📝 إنشاء منشور", "📰 فحص الأخبار"],
     ["📅 الجدولة", "⚙️ لوحة التحكم"]],
    resize_keyboard=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text("هذا بوت خاص بإدارة صفحة Tawwat Chess.")
        return
    await update.message.reply_text(
        "بوت Tawwat Chess يعمل ✅\n\n"
        f"• الأخبار: فحص كل {int(config.NEWS_CHECK_MINUTES)} دقيقة (نسخة عربية + إنجليزية تختار بينهما).\n"
        f"• محرّك الصياغة: {config.active_provider()}\n"
        f"• النشر التلقائي بين {config.POST_WINDOW_START}:00 و{config.POST_WINDOW_END}:00 (العاجل فورًا).",
        reply_markup=MENU)
    await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=_main_menu())


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text("جارٍ فحص الأخبار…")
    await check_news_job(context, force=True, announce_empty=True)


async def cmd_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text("⚙️ لوحة التحكم:", reply_markup=_control_keyboard())


async def cmd_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text("📝 اختر نوع المنشور:", reply_markup=_create_menu())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text("🏠 القائمة الرئيسية:", reply_markup=_main_menu())


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text(_schedule_text(), reply_markup=_back_main_kb())


def _content_cmd(ctype, label):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        await update.message.reply_text(f"جارٍ تجهيز ({label})…")
        res = await asyncio.to_thread(_build_content, ctype)
        if not res:
            await update.message.reply_text("تعذّر التجهيز الآن (قد يكون مصدر اللغز غير متاح حاليًا).")
            return
        img, caption, comment = res
        await deliver(context, img, caption, comment, auto=False, label=label)
    return handler


# ربط أزرار القائمة (reply keyboard) بالأوامر (تُقرأ في on_text)
MENU_ACTIONS = {
    "📝 إنشاء منشور": cmd_create,
    "📰 فحص الأخبار": cmd_check,
    "📅 الجدولة": cmd_schedule,
    "⚙️ لوحة التحكم": cmd_control,
}


from telegram.error import Conflict, NetworkError, TimedOut, RetryAfter


async def on_error(update, context):
    err = context.error
    # أخطاء تشغيلية متكرّرة لا نُغرِق بها تيليجرام (تُسجَّل في الكونسول فقط)
    if isinstance(err, Conflict):
        log.info("Conflict: نسخة أخرى من البوت تعمل بنفس التوكن — أوقف باقي النسخ.")
        return
    if isinstance(err, (NetworkError, TimedOut, RetryAfter)):
        log.info("شبكة مؤقتة: %s", err)
        return
    import traceback
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))[-1500:]
    log.info("خطأ غير متوقّع: %s", err)             # في السجلّ فقط (نرسل التتبّع كاملًا أدناه)
    notify.send_admin(f"خطأ غير متوقّع أثناء التنفيذ:\n{tb}", prefix="❌ خطأ")


# قائمة الأوامر التي تظهر في زرّ «/» داخل تيليجرام
_COMMANDS = [
    BotCommand("start", "تشغيل / إظهار القائمة"),
    BotCommand("menu", "القائمة الرئيسية"),
    BotCommand("create", "إنشاء منشور (تصنيفات)"),
    BotCommand("schedule", "عرض الجدول"),
    BotCommand("check", "فحص الأخبار الآن"),
    BotCommand("tournament", "إعلان بطولة"),
    BotCommand("control", "لوحة التحكم"),
]


async def _post_init(app):
    try:
        await app.bot.set_my_commands(_COMMANDS)
    except Exception as e:
        log.warning("تعذّر ضبط قائمة الأوامر: %s", e)


# ---------------- التشغيل ----------------
def main():
    db.init_db()
    os.makedirs(CARDS_DIR, exist_ok=True)
    start_health_server(config.PORT)

    missing = config.check()
    if missing:
        raise SystemExit("نواقص في ملف .env: " + ", ".join(missing))

    # تحويل أي تحذير/خطأ من وحدات البوت إلى تيليجرام تلقائيًا
    notify.install_telegram_logging()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("create", cmd_create))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("puzzle", _content_cmd("puzzle", "لغز اليوم")))
    app.add_handler(CommandHandler("wisdom", _content_cmd("wisdom", "حكمة شطرنجية")))
    app.add_handler(CommandHandler("classic", _content_cmd("classic", "نقلة من الزمن الجميل")))
    app.add_handler(CommandHandler("tournament", cmd_tournament))
    app.add_handler(CommandHandler("control", cmd_control))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    # جدولة الأخبار (كل NEWS_CHECK_MINUTES دقيقة)
    app.job_queue.run_repeating(check_news_job, interval=config.NEWS_CHECK_MINUTES * 60, first=15)
    # تنظيف يومي للبطاقات القديمة (يمنع امتلاء القرص)
    app.job_queue.run_repeating(cleanup_job, interval=86400, first=3600)
    # جدولة المحتوى الأسبوعي
    tz = ZoneInfo(config.TIMEZONE)
    for item in config.SCHEDULE:
        t = datetime.time(hour=item["hour"], minute=item["minute"], tzinfo=tz)
        app.job_queue.run_daily(scheduled_job, time=t, days=item["days"],
                                data=item["type"], name=f"sched_{item['type']}_{item['days']}")
    if not config.llm_ready():
        log.warning("تنبيه: محرّك صياغة الأخبار غير مضبوط (الأخبار لن تُصاغ). "
                    "املأ LLM_API_BASE أو ANTHROPIC_API_KEY في .env. "
                    "بقية المحتوى المجدول يعمل عادي.")
    log.info("محرّك الصياغة: %s", config.active_provider())
    log.info("تشغيل البوت… (المحتوى المجدول: %d مهمة)", len(config.SCHEDULE))
    notify.send_admin("البوت اشتغل ✅ — تنبيهات الأخطاء مفعّلة.", prefix="ℹ️")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        notify.send_admin("توقّف البوت بخطأ فادح:\n"
                          + "".join(traceback.format_exc())[-1500:], prefix="❌ خطأ")
        raise
