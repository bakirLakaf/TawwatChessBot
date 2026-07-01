# -*- coding: utf-8 -*-
"""
جلب أخبار الشطرنج من مصادر RSS.
- يلتقط الجديد فقط (يقارن بقاعدة البيانات).
- يستخرج صورة الخبر إن وُجدت.

ملاحظة مهمة: روابط RSS قد تتغيّر مع الوقت. رابط Chess.com مؤكّد؛
الباقي قد يحتاج تعديلًا — البوت يتجاوز أي مصدر معطوب تلقائيًا.
عدّل القائمة FEEDS بحرّية وأضف مصادرك المفضّلة.
"""
import re
import html
import time
import calendar
import hashlib
import logging
import feedparser
import requests
import config
import database as db
import players

log = logging.getLogger(__name__)

# صورة المقال من وسوم og:image / twitter:image (بأي ترتيب للسمتين)
_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*'
    r'content=["\']([^"\']+)["\']', re.I)
_OG_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
    r'(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I)
_IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
# روابط صور غير مناسبة (شعارات/أيقونات/إعلانات/فواصل) — نتجاهلها
_JUNK_IMG = re.compile(r'(logo|avatar|sprite|placeholder|/ads?/|advert|pixel|spacer|1x1|\.svg)', re.I)

# (الاسم المعروض, رابط RSS)
FEEDS = [
    ("Chess.com", "https://www.chess.com/rss/news"),      # مؤكّد
    ("ChessBase", "https://en.chessbase.com/feed"),       # تحقّق
    ("FIDE", "https://www.fide.com/feed"),                # تحقّق
    # ("Lichess", "https://lichess.org/blog.atom"),       # فعّله بعد التأكد من الرابط
    # ("TWIC", "https://theweekinchess.com/twic"),        # فعّله بعد التأكد من الرابط
]

MAX_PER_FEED = 8  # كم خبرًا نفحص من كل مصدر في كل مرة


def _clean(text):
    """إزالة وسوم HTML والمسافات الزائدة."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_image(entry):
    """محاولة استخراج رابط صورة من عنصر الخبر."""
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media and isinstance(media, list) and media[0].get("url"):
            return media[0]["url"]
    for enc in entry.get("enclosures", []) or []:
        if "image" in (enc.get("type") or "") and enc.get("href"):
            return enc["href"]
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and "image" in (link.get("type") or ""):
            return link.get("href")
    blob = entry.get("summary", "") or ""
    if entry.get("content"):
        blob += entry["content"][0].get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob)
    return m.group(1) if m else None


def _og_image(link):
    """أفضل صورة لمقال من صفحته: og/twitter أولًا ثم صور جسم المقال،
    مع تجاهل الشعارات/الأيقونات/الإعلانات. (احتياط حين لا تضع خلاصة RSS صورة)."""
    if not link:
        return None
    try:
        r = requests.get(link, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        page = r.text
        candidates = []
        for rx in (_OG_RE, _OG_RE_REV):       # الأولوية لصورة الميتا (الأنسب عادةً)
            m = rx.search(page)
            if m:
                candidates.append(m.group(1))
        candidates += _IMG_SRC.findall(page)  # ثم صور جسم المقال كاحتياط
        for u in candidates:
            u = html.unescape((u or "").strip())
            if u.startswith("//"):
                u = "https:" + u
            if not u.startswith("http") or _JUNK_IMG.search(u):
                continue
            return u
    except Exception as e:
        log.warning("تعذّر جلب صورة المقال %s: %s", link, e)
    return None


# كلمات تدلّ على خبر عاجل/حصري (يُنشَر فورًا ولا يؤجَّل)
_BREAKING_RE = re.compile(
    r'\b(win|wins|won|champion|clinch|clinches|defeat|defeats|beat|beats|'
    r'qualif|begins|starts|kicks off|underway|title|crowned|record|'
    r'announce|dies|passes away)\b'
    r'|فاز|يفوز|بطل|يتوّج|توّج|يحسم|حسم|ينطلق|انطلاق|انطلقت|تُوّج|رحيل|وفاة', re.I)


def _is_breaking(text):
    return bool(_BREAKING_RE.search(text or ""))


def _published_epoch(entry):
    """طابع زمني (ثوانٍ) لتاريخ نشر الخبر، أو None إن غاب."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return calendar.timegm(t)   # struct_time (UTC) → epoch
            except Exception:
                pass
    return None


def _sort_key(art):
    """العاجل أولًا، ثم العرب، ثم العالميون، ثم الأحدث نشرًا."""
    return (1 if art.get("breaking") else 0,
            1 if art.get("arab_hits") else 0,
            1 if art.get("world_hits") else 0,
            art.get("published") or 0)


def fetch_new(limit, ignore_seen=False):
    """يعيد أهمّ الأخبار حتى الحد limit (مرتّبة: عاجل ← عرب ← عالميون ← الأحدث).

    افتراضيًا يتجاهل المرئية سابقًا والقديمة. مع ignore_seen=True يُرجِع أحدث
    الأخبار حتى لو سبق نشرها (لزرّ «خبر الآن» عند الطلب)."""
    now = time.time()
    max_age = config.NEWS_MAX_AGE_HOURS * 3600
    candidates = []
    for source_name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            log.warning("تعذّر قراءة المصدر %s: %s", source_name, e)
            continue
        if getattr(feed, "bozo", 0) and not feed.entries:
            log.warning("المصدر %s لم يُرجِع عناصر (الرابط قد يحتاج تعديلًا).", source_name)
            continue
        for entry in feed.entries[:MAX_PER_FEED]:
            link = entry.get("link", "")
            if not link:
                continue
            h = hashlib.sha1(link.encode("utf-8")).hexdigest()
            if not ignore_seen and db.is_seen(h):
                continue
            published = _published_epoch(entry)
            # بلا تاريخ نشر لا يمكن ضمان حداثة الخبر، فيُستبعد كالقديم تمامًا
            if published is None or (now - published) > max_age:
                if not ignore_seen:
                    db.mark_seen(h, "(قديم/بلا تاريخ)")  # نعلّمه مرئيًا حتى لا نفحصه مجددًا
                continue
            title = _clean(entry.get("title", ""))
            summary = _clean(entry.get("summary", ""))[:1200]
            world_hits, arab_hits = players.classify(title + " . " + summary)
            candidates.append({
                "source": source_name,
                "title": title,
                "summary": summary,
                "link": link,
                "hash": h,
                "image": _entry_image(entry),
                "world_hits": world_hits,
                "arab_hits": arab_hits,
                "published": published,
                "breaking": _is_breaking(title + " . " + summary),
            })
    candidates.sort(key=_sort_key, reverse=True)
    featured = sum(1 for a in candidates if a.get("arab_hits") or a.get("world_hits"))
    breaking = sum(1 for a in candidates if a.get("breaking"))
    selected = candidates[:limit]
    # جلب صورة المقال من صفحته للمحدّدين فقط حين لا تأتي صورة من RSS
    for art in selected:
        if not art.get("image"):
            art["image"] = _og_image(art["link"])
    if candidates:
        log.info("مرشّحون: %d (بارزون/عرب: %d، عاجل: %d). نأخذ أهمّ %d.",
                 len(candidates), featured, breaking, len(selected))
    return selected
