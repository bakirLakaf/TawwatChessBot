# -*- coding: utf-8 -*-
"""
تنبيهات الأخطاء على تيليجرام.

- send_admin(text): يرسل رسالة لمحادثة المشرف عبر Telegram Bot API مباشرةً
  (HTTP)، فيعمل من أي خيط دون الحاجة لحلقة asyncio.
- install_telegram_logging(): يربط معالج تسجيل يحوّل أي تحذير/خطأ (WARNING+)
  من وحدات البوت إلى تيليجرام تلقائيًا، مع:
    * تجاهل ضجيج المكتبات الخارجية (telegram/httpx/urllib3/apscheduler…)
    * كبح التكرار (لا تُرسل نفس الرسالة أكثر من مرة خلال نافذة قصيرة)
"""
import time
import logging
import requests
import config

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"

# كبح التكرار: آخر إرسال لكل نص (نص -> طابع زمني)
_recent = {}
_DEDUP_WINDOW = 120        # ثانية: لا تُكرّر نفس الرسالة خلالها
_MAX_LEN = 3500            # حدّ طول رسالة تيليجرام (الحدّ 4096)

# وحدات خارجية لا نريد تحويل تحذيراتها إلى تيليجرام (ضجيج/تكرار)
_MUTED_PREFIXES = ("telegram", "httpx", "httpcore", "urllib3", "apscheduler",
                   "asyncio", "tzlocal", "notify")


def send_admin(text, prefix="⚠️"):
    """يرسل تنبيهًا لمحادثة المشرف. صامت إن لم تُضبط بيانات تيليجرام."""
    token = config.TELEGRAM_BOT_TOKEN
    chat = config.TELEGRAM_ADMIN_CHAT_ID
    if not token or not chat:
        return False
    msg = f"{prefix} {text}".strip()[:_MAX_LEN]
    now = time.time()
    # كبح التكرار + تنظيف القديم
    last = _recent.get(msg)
    if last and (now - last) < _DEDUP_WINDOW:
        return False
    _recent[msg] = now
    if len(_recent) > 200:
        for k, t in list(_recent.items()):
            if now - t > _DEDUP_WINDOW:
                _recent.pop(k, None)
    try:
        requests.post(_API.format(token=token),
                      data={"chat_id": chat, "text": msg,
                            "disable_web_page_preview": True},
                      timeout=20)
        return True
    except Exception:
        return False  # لا نرفع خطأً داخل مسار الإبلاغ عن الأخطاء


class _TelegramHandler(logging.Handler):
    """يحوّل سجلّات WARNING+ من وحدات البوت إلى تيليجرام."""
    def emit(self, record):
        try:
            if record.levelno < logging.WARNING:
                return
            name = record.name or ""
            if any(name == p or name.startswith(p + ".") for p in _MUTED_PREFIXES):
                return
            level = "❌ خطأ" if record.levelno >= logging.ERROR else "⚠️ تنبيه"
            send_admin(f"{record.getMessage()}\n\n[{name}]", prefix=level)
        except Exception:
            pass  # المعالِج لا يجب أن يُسقِط البرنامج أبدًا


def install_telegram_logging(level=logging.WARNING):
    """يربط المعالج بالجذر مرّة واحدة. يلتقط تحذيرات/أخطاء وحدات البوت فقط."""
    root = logging.getLogger()
    if any(isinstance(h, _TelegramHandler) for h in root.handlers):
        return
    h = _TelegramHandler()
    h.setLevel(level)
    root.addHandler(h)
    log.info("تنبيهات الأخطاء على تيليجرام مفعّلة.")
