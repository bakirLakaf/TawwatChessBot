# -*- coding: utf-8 -*-
"""
مطابقة أسماء اللاعبين في نص الخبر (للتركيز على أبرز اللاعبين).

- data/top_players.json : أبرز اللاعبين عالميًا (تصنيف FIDE الكلاسيكي).
- data/arab_players.json : أبرز اللاعبين العرب.

كل عنصر: {"name": "الاسم", "aliases": ["تهجئة1", "تهجئة2", ...]}.
المطابقة على المرادفات: حدود كلمات للحروف اللاتينية (تفادي مطابقات جزئية)،
ومطابقة نصية مباشرة للعربية. غير حسّاسة لحالة الأحرف.

الاستخدام:
    world_hits, arab_hits = players.classify(title + " " + summary)
    # world_hits / arab_hits : قوائم بأسماء اللاعبين المذكورين (قد تكون فارغة).

عدّل ملفّي JSON بحرية لإضافة/حذف لاعبين — لا حاجة لتعديل الكود.
"""
import os
import re
import json
import logging

log = logging.getLogger(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

_AR_CHAR = re.compile(r"[؀-ۿ]")


def _load(name):
    path = os.path.join(DATA, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("قائمة اللاعبين غير موجودة: %s (سيُتجاهَل التركيز).", name)
        return []
    except Exception as e:
        log.warning("تعذّر قراءة %s: %s", name, e)
        return []


def _compile(players):
    """يبني لكل لاعب قائمة أنماط regex من مرادفاته."""
    compiled = []
    for p in players or []:
        name = (p.get("name") or "").strip()
        aliases = list(p.get("aliases") or [])
        if name and name not in aliases:
            aliases.append(name)
        pats = []
        for a in aliases:
            a = (a or "").strip()
            if not a:
                continue
            if _AR_CHAR.search(a):              # عربي: مطابقة نصية مباشرة
                pats.append(re.compile(re.escape(a)))
            else:                                # لاتيني: حدود كلمات، غير حسّاس للحالة
                pats.append(re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.IGNORECASE))
        if pats and name:
            compiled.append((name, pats))
    return compiled


# تحميل كسول (مرة واحدة) مع إمكان إعادة التحميل
_world = None
_arab = None


def _world_list():
    global _world
    if _world is None:
        _world = _compile(_load("top_players.json"))
        log.info("حُمِّل %d لاعبًا عالميًا للتركيز.", len(_world))
    return _world


def _arab_list():
    global _arab
    if _arab is None:
        _arab = _compile(_load("arab_players.json"))
        log.info("حُمِّل %d لاعبًا عربيًا للتركيز.", len(_arab))
    return _arab


def reload_lists():
    """إعادة تحميل القائمتين من القرص (بعد تعديل ملفات JSON)."""
    global _world, _arab
    _world = _arab = None
    return len(_world_list()), len(_arab_list())


def _match(text, compiled):
    if not text:
        return []
    hits = []
    for name, pats in compiled:
        if any(rx.search(text) for rx in pats):
            hits.append(name)
    return hits


def classify(text):
    """يعيد (world_hits, arab_hits): أسماء اللاعبين العالميين/العرب المذكورين في النص."""
    return _match(text, _world_list()), _match(text, _arab_list())
