# -*- coding: utf-8 -*-
"""تحميل إعدادات البوت من ملف .env (لا توضع المفاتيح في الكود)."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- تيليجرام ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()

# --- مزوّد إعادة الصياغة (LLM) ---
# الخيار أ (مجاني عادةً): أي خدمة متوافقة مع OpenAI — Gemini / bynara / OpenRouter ...
#   إن ضُبط LLM_API_BASE فسيُستعمل هذا المزوّد (له الأولوية).
LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()   # مثل https://router.bynara.id/v1
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()          # مثل mimo-v2.5-free أو gemini-2.5-flash

# الخيار ب (مدفوع): Claude مباشرة — يُستعمل فقط إذا لم يُضبط LLM_API_BASE.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()


def llm_ready():
    """هل خدمة إعادة الصياغة (لازمة للأخبار) مضبوطة؟"""
    return bool(LLM_API_BASE and LLM_API_KEY and LLM_MODEL) or bool(ANTHROPIC_API_KEY)


def active_provider():
    if LLM_API_BASE:
        return f"OpenAI-compatible ({LLM_MODEL})"
    if ANTHROPIC_API_KEY:
        return f"Claude ({CLAUDE_MODEL})"
    return "غير مضبوط"

# --- فيسبوك ---
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()

# --- الأخبار ---
NEWS_CHECK_MINUTES = float(os.getenv("NEWS_CHECK_MINUTES", "20"))   # فحص كل 20 دقيقة
MAX_POSTS_PER_CHECK = int(os.getenv("MAX_POSTS_PER_CHECK", "3"))
AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "false").lower() == "true"  # نشر الأخبار بلا موافقة
# تجاهل أي خبر أقدم من هذه المدة (بالساعات) حتى لا نُحرَج بأخبار قديمة
NEWS_MAX_AGE_HOURS = float(os.getenv("NEWS_MAX_AGE_HOURS", "72"))

# --- المحتوى المجدول (ألغاز/حكم/نقلات/بطولة) ---
# false = يُرسل لك للموافقة في وقته (آمن للتجربة). true = نشر تلقائي هادئ في وقته.
SCHEDULED_AUTO_PUBLISH = os.getenv("SCHEDULED_AUTO_PUBLISH", "false").lower() == "true"

# المنطقة الزمنية (الجزائر UTC+1)
TIMEZONE = os.getenv("TIMEZONE", "Africa/Algiers")

# --- نافذة النشر (نشر تلقائي فقط بين هاتين الساعتين بتوقيت الجزائر) ---
# الأخبار العاجلة تتجاوز هذه النافذة وتُنشَر فورًا.
POST_WINDOW_START = int(os.getenv("POST_WINDOW_START", "8"))   # 8 صباحًا
POST_WINDOW_END = int(os.getenv("POST_WINDOW_END", "22"))      # 10 مساءً

# --- تشغيل ---
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "tawwat_bot.db")

# ============================================================
# الجدول الأسبوعي. الأيام: 0=الأحد 1=الإثنين 2=الثلاثاء 3=الأربعاء 4=الخميس 5=الجمعة 6=السبت
# عدّل الأوقات/الأيام كما تشاء (راجع إحصاءات صفحتك لأفضل توقيت).
# ============================================================
SCHEDULE = [
    {"type": "classic",    "hour": 21, "minute": 0, "days": (0,)},
    {"type": "wisdom",     "hour": 13, "minute": 0, "days": (1,)},
    {"type": "puzzle",     "hour": 21, "minute": 0, "days": (2,)},
    {"type": "wisdom",     "hour": 13, "minute": 0, "days": (3,)},
    {"type": "classic",    "hour": 21, "minute": 0, "days": (4,)},
    {"type": "tournament", "hour": 21, "minute": 0, "days": (5,)},
    {"type": "puzzle",     "hour": 21, "minute": 0, "days": (6,)},
]


def check():
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    elif TELEGRAM_BOT_TOKEN.startswith("EAA") or ":" not in TELEGRAM_BOT_TOKEN:
        # توكن تيليجرام صيغته «أرقام:حروف»؛ توكن فيسبوك يبدأ بـ EAA
        missing.append("TELEGRAM_BOT_TOKEN يبدو خاطئًا (ربما وضعتَ توكن فيسبوك مكانه! "
                       "توكن تيليجرام من @BotFather صيغته «123456:ABC...»)")
    if not TELEGRAM_ADMIN_CHAT_ID:
        missing.append("TELEGRAM_ADMIN_CHAT_ID")
    if FB_PAGE_ACCESS_TOKEN and not FB_PAGE_ACCESS_TOKEN.startswith("EAA"):
        missing.append("FB_PAGE_ACCESS_TOKEN يبدو خاطئًا (توكن فيسبوك يبدأ بـ EAA)")
    return missing
