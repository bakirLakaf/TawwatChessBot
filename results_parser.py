# -*- coding: utf-8 -*-
"""
تحليل نتائج بطولة مُدخَلة يدويًا كنص في تيليجرام.
كل سطر = لاعب واحد، والحقول مفصولة بفاصلة عربية «،» أو فاصلة عادية «,»
بهذا الترتيب: الترتيب، الاسم، النقاط، [التصنيف]، [الدولة/النادي]

مثال:
    1،علاء الدين بورلناس،7،2345
    2،محمد بن صالح،6.5،2210
    3،يوسف العماري،6
"""
import re

_SPLIT_RE = re.compile(r"[،,]")


def parse_manual(text):
    """يعيد قائمة dict: [{rank, name, points, rating, fed}, ...].
    يتجاهل الأسطر غير الصالحة (بدل أن يتوقف بخطأ) حتى لو أخطأ المستخدم بسطر واحد."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in _SPLIT_RE.split(line) if p.strip() != ""]
        if len(parts) < 2:
            continue  # سطر ناقص (يحتاج ترتيب + اسم على الأقل)
        rank = parts[0]
        name = parts[1]
        points = parts[2] if len(parts) > 2 else ""
        rating = parts[3] if len(parts) > 3 else ""
        fed = parts[4] if len(parts) > 4 else ""
        if not name:
            continue
        rows.append({"rank": rank, "name": name, "points": points,
                     "rating": rating, "fed": fed})
    return rows
