# -*- coding: utf-8 -*-
"""النشر على صفحة فيسبوك عبر Graph API (نشر صورة مع نص)."""
import logging
import requests
import config

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"


def publish_photo(image_path, caption):
    """
    ينشر صورة مع نص على الصفحة.
    يعيد (True, post_id) عند النجاح، أو (False, رسالة الخطأ) عند الفشل.
    """
    if not config.FB_PAGE_ID or not config.FB_PAGE_ACCESS_TOKEN:
        return False, "إعدادات فيسبوك غير مكتملة (FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN)."
    url = f"{GRAPH}/{config.FB_PAGE_ID}/photos"
    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                url,
                data={"caption": caption, "access_token": config.FB_PAGE_ACCESS_TOKEN},
                files={"source": f},
                timeout=90,
            )
    except Exception as e:
        return False, f"تعذّر الاتصال بفيسبوك: {e}"
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code == 200 and ("post_id" in j or "id" in j):
        return True, j.get("post_id") or j.get("id")
    err = (j.get("error") or {}).get("message", f"HTTP {r.status_code}")
    if "pages_manage_posts" in err or "permission" in err.lower():
        err += ("\n\n💡 الحل: التوكن لا يملك صلاحية النشر. ولّد Page Access Token جديدًا "
                "بصلاحيات pages_manage_posts + pages_read_engagement (أنت أدمن الصفحة، "
                "والتطبيق في وضع Development)، ثم ضعه في FB_PAGE_ACCESS_TOKEN.")
    log.warning("فشل النشر على فيسبوك: %s", err)
    return False, err


def add_comment(post_id, message):
    """إضافة تعليق على منشور (يُستعمل لاحقًا لوضع حل اللغز في أول تعليق)."""
    url = f"{GRAPH}/{post_id}/comments"
    try:
        r = requests.post(url, data={"message": message,
                                     "access_token": config.FB_PAGE_ACCESS_TOKEN}, timeout=60)
        return r.status_code == 200
    except Exception as e:
        log.warning("تعذّر إضافة التعليق: %s", e)
        return False
