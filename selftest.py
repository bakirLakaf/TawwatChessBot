# -*- coding: utf-8 -*-
"""
اختبار ذاتي شامل لبوت Tawwat Chess.

يفحص: الإعدادات · قاعدة البيانات · مطابقة اللاعبين · القالب (كل الهويات + RTL)
· الألغاز (Lichess) · المحتوى المجدول · الأخبار (RSS + الصور) · الصياغة (LLM)
· استيراد البوت والقوائم.

لا يلمس قاعدتك الحقيقية (يستعمل قاعدة مؤقتة) ولا ينشر على فيسبوك.
الصور التجريبية تُحفظ في cards/selftest_*.jpg لتفحصها بعينك.

التشغيل:  python selftest.py
ثم انسخ كل المخرجات وأرسلها.
"""
import os
import sys
import io

# قاعدة بيانات مؤقتة حتى لا نلمس الحقيقية
os.environ.setdefault("DB_PATH", "selftest_tmp.db")
import config
config.DB_PATH = "selftest_tmp.db"
if os.path.exists(config.DB_PATH):
    os.remove(config.DB_PATH)

PASS, FAIL = 0, 0
SKIP = 0


def check(name, fn):
    global PASS, FAIL
    try:
        msg = fn()
        PASS += 1
        print(f"✅ {name}" + (f"  — {msg}" if msg else ""))
    except Exception as e:
        FAIL += 1
        print(f"❌ {name}  — {type(e).__name__}: {e}")


def skip(name, why):
    global SKIP
    SKIP += 1
    print(f"⏭️  {name}  — تخطّي: {why}")


def section(t):
    print("\n" + "=" * 48 + f"\n{t}\n" + "=" * 48)


# ----------------------------------------------------------
section("1) الإعدادات")
check("تحميل config", lambda: f"المزوّد: {config.active_provider()}")
check("مفاتيح تيليجرام موجودة",
      lambda: "ناقص: " + ", ".join(config.check()) if config.check() else "مكتملة")
check("محرّك الصياغة مضبوط (للأخبار)",
      lambda: "مضبوط" if config.llm_ready() else (_ for _ in ()).throw(Exception("غير مضبوط — الأخبار لن تُصاغ")))
check("نافذة النشر",
      lambda: f"{config.POST_WINDOW_START}:00–{config.POST_WINDOW_END}:00 · فحص كل {int(config.NEWS_CHECK_MINUTES)}د")

# ----------------------------------------------------------
section("2) قاعدة البيانات")
import database as db
check("init_db + الترقية", lambda: db.init_db() or "تم")


def _db_roundtrip():
    db.add_pending("st1", "a.jpg", "نص عربي", "", None,
                   alt_image_path="e.jpg", alt_caption="English", lang="ar",
                   event="Test Cup 2026", category="result")
    p = db.get_pending("st1")
    assert p["event"] == "Test Cup 2026" and p["category"] == "result"
    nl = db.swap_pending_lang("st1")
    assert nl == "en" and db.get_pending("st1")["caption"] == "English"
    db.set_images("st1", "new.jpg", "newalt.jpg")
    assert db.get_pending("st1")["image_path"] == "new.jpg"
    return "إضافة/تبديل لغة/تبديل صورة: سليم"


check("عمليات pending (نسختان + هوية)", _db_roundtrip)
check("الإحصاءات", lambda: str(db.stats()))

# ----------------------------------------------------------
section("3) مطابقة اللاعبين")
import players
check("تحميل القوائم",
      lambda: f"{len(players._world_list())} عالمي · {len(players._arab_list())} عربي")


def _match():
    w, a = players.classify("Magnus Carlsen beats Bassem Amin")
    assert "Magnus Carlsen" in w and "Bassem Amin" in a
    w2, a2 = players.classify("The Arab Chess Championship begins")  # لا لاعب
    assert not a2, "مطابقة خاطئة لكلمة Arab"
    return "كارلسن+أمين مكتشفان · لا مطابقة خاطئة لـ Arab"


check("classify (صحّة + لا إيجابيات كاذبة)", _match)

# ----------------------------------------------------------
section("4) القالب والهويات (RTL)")
import bot
import template
os.makedirs("cards", exist_ok=True)


def _render(name, data, lang="ar"):
    p = bot._make_news_card(data, None, f"selftest_{name}", lang)
    assert os.path.exists(p) and os.path.getsize(p) > 5000
    return os.path.basename(p)


check("بطاقة RTL (لاتيني+عربي مختلط)",
      lambda: _render("rtl", {"title": "Buettner يتقدم لرئاسة FIDE",
                              "event": "FIDE Election", "category": "statement"}))
check("هوية: إنجاز عربي",
      lambda: _render("arab", {"title": "Bassem Amin يحرز اللقب",
                               "event": "African Championship", "category": "arab_achievement"}))
check("هوية: بطولة (عنوان حدث طويل → تصغير)",
      lambda: _render("tour", {"title": "Gukesh في الصدارة",
                               "event": "Tata Steel Masters Wijk aan Zee 2026", "category": "tournament"}))
check("هوية: أخبار عالمية", lambda: _render("world", {"title": "خبر عام", "category": "world_general"}))
check("بطاقة إنجليزية", lambda: _render("en", {"title": "Firouzja Wins Again",
                                              "event": "Norway Chess", "category": "result"}, "en"))
check("كل تصنيفات NEWS_THEMES تعمل",
      lambda: ", ".join(c for c in bot.NEWS_THEMES
                        if _render("th_" + c, {"title": "اختبار", "event": "E", "category": c})))

# ----------------------------------------------------------
section("5) الألغاز (Lichess — شبكة)")
import lichess_puzzle as lp


def _daily():
    d = lp.get_daily_puzzle()
    assert d and d.get("solution"), "تعذّر جلب/تحليل لغز اليوم"
    return f"{d['turn']} · الحل: {d['solution']} · تقييم {d.get('rating')}"


check("لغز اليوم (تحليل الوضعية)", _daily)


def _next(diff):
    p = lp.get_puzzle(diff)
    if not p:
        raise Exception("429 أو تعذّر (طبيعي إن كان الـIP مضغوطًا — يعمل على Railway)")
    return f"تقييم {p.get('rating')} · {p.get('themes')}"


check("لغز عشوائي صعب (/next)", lambda: _next("hard"))

# ----------------------------------------------------------
section("6) المحتوى المجدول")
import content


def _ok_card(res):
    assert res, "أرجع None"
    img, caption, comment = res
    assert os.path.exists(img), "لم تُنشأ الصورة"
    return caption.split("\n")[0][:50]


check("حكمة", lambda: _ok_card(content.make_wisdom()))
check("نقلة من الزمن الجميل", lambda: _ok_card(content.make_classic()))
check("إعلان بطولة (افتراضي)", lambda: _ok_card(content.make_tournament()))
check("لغز متوسط (مع احتياط لغز اليوم)", lambda: _ok_card(content.make_puzzle("medium")))


# ----------------------------------------------------------
section("7) الأخبار (RSS + الصور + الفلترة)")
import news_sources as ns


def _feeds():
    out = []
    for nm, url in ns.FEEDS:
        import feedparser
        f = feedparser.parse(url)
        out.append(f"{nm}:{len(f.entries)}")
    return " · ".join(out)


check("قراءة مصادر RSS", _feeds)


def _fetch():
    arts = ns.fetch_new(3)
    if not arts:
        return "لا أخبار جديدة الآن (أو كلها مرئية/قديمة)"
    a = arts[0]
    return (f"{len(arts)} خبر · أول: '{a['title'][:35]}' · صورة: "
            f"{'نعم' if a.get('image') else 'لا'} · عاجل: {a.get('breaking')}")


check("fetch_new (أولوية + صورة + عاجل + تاريخ)", _fetch)

# ----------------------------------------------------------
section("8) الصياغة بالعربية والإنجليزية (LLM)")
import rewriter
_sample = {"source": "Chess.com", "title": "Magnus Carlsen wins Norway Chess 2026",
           "summary": "Magnus Carlsen clinched the title after beating Fabiano Caruana in the final round.",
           "link": "https://example.com", "world_hits": ["Magnus Carlsen", "Fabiano Caruana"],
           "arab_hits": []}

if not config.llm_ready():
    skip("صياغة عربية", "LLM غير مضبوط في .env")
    skip("صياغة إنجليزية", "LLM غير مضبوط في .env")
else:
    def _ar():
        d = rewriter.to_arabic(_sample)
        return f"عنوان='{d.get('title')}' · حدث='{d.get('event')}' · تصنيف={d.get('category')}"
    check("صياغة عربية (title/event/category)", _ar)

    def _en():
        d = rewriter.to_english(_sample)
        return f"title='{d.get('title')}' · event='{d.get('event')}'"
    check("صياغة إنجليزية", _en)

# ----------------------------------------------------------
section("9) البوت والقوائم")
check("استيراد bot", lambda: "تم")
check("القوائم التفاعلية تُبنى",
      lambda: f"رئيسية:{len(bot._main_menu().inline_keyboard)} · إنشاء:{len(bot._create_menu().inline_keyboard)} · لغز:{len(bot._puzzle_menu().inline_keyboard)}")
check("منطق الهوية (_resolve_category)",
      lambda: "سليم" if (bot._resolve_category("result", True) == "arab_achievement"
                         and bot._resolve_category("general", False) == "world_general") else (_ for _ in ()).throw(Exception("خطأ")))
check("نص الجدول", lambda: bot._schedule_text().split("\n")[0])
check("كشف العاجل",
      lambda: "سليم" if (ns._is_breaking("Gukesh wins title") and not ns._is_breaking("a quiet game")) else (_ for _ in ()).throw(Exception("خطأ")))

# ----------------------------------------------------------
section("النتيجة")
print(f"\n✅ نجح: {PASS}   ❌ فشل: {FAIL}   ⏭️ تخطّي: {SKIP}")
print("الصور التجريبية في مجلد cards/ (selftest_*.jpg) — افحصها بصريًا (خصوصًا RTL).")
print("\nانسخ كل ما فوق وأرسله.")

# تنظيف القاعدة المؤقتة
try:
    os.remove(config.DB_PATH)
except OSError:
    pass
