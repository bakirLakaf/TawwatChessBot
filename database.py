# -*- coding: utf-8 -*-
"""
قاعدة بيانات SQLite:
- seen: الأخبار التي سبق التقاطها (منع التكرار)
- pending: المنشورات الجاهزة بانتظار قرارك (مع حقل comment لحل اللغز)
- state: مؤشّرات بسيطة (لتدوير الحكم/المباريات)
"""
import sqlite3
import datetime
import config


def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS seen(
            link_hash TEXT PRIMARY KEY, title TEXT, ts TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pending(
            token TEXT PRIMARY KEY, image_path TEXT, caption TEXT,
            source_url TEXT, comment TEXT, status TEXT, ts TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS state(
            key TEXT PRIMARY KEY, value TEXT)""")
        # ترقية: أعمدة النسخة البديلة + هوية الخبر (الحدث/التصنيف)
        have = {r[1] for r in c.execute("PRAGMA table_info(pending)")}
        for col in ("alt_image_path", "alt_caption", "lang", "event", "category"):
            if col not in have:
                c.execute(f"ALTER TABLE pending ADD COLUMN {col} TEXT")


def _now():
    return datetime.datetime.utcnow().isoformat()


# ---------- الأخبار ----------
def is_seen(link_hash):
    with _conn() as c:
        return c.execute("SELECT 1 FROM seen WHERE link_hash=?", (link_hash,)).fetchone() is not None


def mark_seen(link_hash, title):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO seen(link_hash,title,ts) VALUES(?,?,?)",
                  (link_hash, title, _now()))


# ---------- المنشورات المعلّقة ----------
def add_pending(token, image_path, caption, source_url="", comment=None,
                alt_image_path=None, alt_caption=None, lang=None,
                event=None, category=None):
    """يضيف منشورًا معلّقًا. للأخبار ثنائية اللغة: مرّر alt_* (النسخة الأخرى) و lang.
    event/category: هوية الخبر (تُستعمل لإعادة بناء البطاقة عند تعديل الصورة)."""
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO pending(
                       token,image_path,caption,source_url,comment,status,ts,
                       alt_image_path,alt_caption,lang,event,category)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (token, image_path, caption, source_url, comment, "pending", _now(),
                   alt_image_path, alt_caption, lang, event, category))


def get_pending(token):
    with _conn() as c:
        r = c.execute("SELECT * FROM pending WHERE token=?", (token,)).fetchone()
        return dict(r) if r else None


def set_status(token, status):
    with _conn() as c:
        c.execute("UPDATE pending SET status=? WHERE token=?", (status, token))


def set_caption(token, caption):
    with _conn() as c:
        c.execute("UPDATE pending SET caption=? WHERE token=?", (caption, token))


def set_images(token, image_path, alt_image_path=None):
    """تحديث صورة المنشور (وصورة النسخة البديلة إن مُرِّرت)."""
    with _conn() as c:
        if alt_image_path is not None:
            c.execute("UPDATE pending SET image_path=?, alt_image_path=? WHERE token=?",
                      (image_path, alt_image_path, token))
        else:
            c.execute("UPDATE pending SET image_path=? WHERE token=?", (image_path, token))


def swap_pending_lang(token):
    """يبدّل النسخة المعروضة بالبديلة (صورة + نص + لغة) لخبر ثنائي اللغة."""
    with _conn() as c:
        r = c.execute("SELECT image_path,caption,alt_image_path,alt_caption,lang "
                      "FROM pending WHERE token=?", (token,)).fetchone()
        if not r or not r["alt_caption"]:
            return None
        new_lang = "en" if (r["lang"] or "ar") == "ar" else "ar"
        c.execute("""UPDATE pending SET image_path=?, caption=?,
                       alt_image_path=?, alt_caption=?, lang=? WHERE token=?""",
                  (r["alt_image_path"], r["alt_caption"],
                   r["image_path"], r["caption"], new_lang, token))
        return new_lang


# ---------- إحصاءات ----------
def stats():
    with _conn() as c:
        seen = c.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
        rows = c.execute("SELECT status, COUNT(*) c FROM pending GROUP BY status").fetchall()
        by_status = {r["status"]: r["c"] for r in rows}
        return {"seen": seen, "by_status": by_status}


# ---------- مؤشّرات التدوير ----------
def get_state(key, default="0"):
    with _conn() as c:
        r = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_state(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, str(value)))
