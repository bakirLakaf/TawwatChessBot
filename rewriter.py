# -*- coding: utf-8 -*-
"""
تحويل خبر شطرنج (إنجليزي غالبًا) إلى منشور عربي بأسلوب صفحة Tawwat Chess.

يدعم مزوّدين (يُختار حسب .env):
  أ) أي خدمة متوافقة مع OpenAI (مجانية عادةً): Gemini / bynara / OpenRouter ...
     عبر LLM_API_BASE + LLM_API_KEY + LLM_MODEL   (لها الأولوية)
  ب) Claude مباشرة (مدفوع): ANTHROPIC_API_KEY + CLAUDE_MODEL

قواعد صارمة لمنع اختراع المعلومات.
"""
import re
import json
import logging
import config

log = logging.getLogger(__name__)
_openai_client = None
_anthropic_client = None

# حروف من كتابات لا مكان لها في منشور عربي/إنجليزي (صيني/ياباني/كوري/سيريلي…)
# نزيلها دفاعيًا حتى لو أخرجها النموذج المجاني بالخطأ.
_BAD_SCRIPTS = re.compile(
    r"[Ѐ-ӿԀ-ԯ"          # سيريلي
    r"　-ヿ㐀-䶿一-鿿豈-﫿"  # CJK + كانا
    r"가-힯＀-￯]+")        # هانغول + عرض كامل


def _sanitize(t):
    """يزيل الحروف الصينية/السيريلية ويضبط المسافات."""
    if not t:
        return t
    return re.sub(r"\s{2,}", " ", _BAD_SCRIPTS.sub("", t)).strip()


SYSTEM = """أنت محرّر صفحة "Tawwat Chess" على فيسبوك، متخصّص بأخبار الشطرنج العربي والعالمي.
مهمتك: تحويل خبر شطرنج (بالإنجليزية غالبًا) إلى منشور عربي قصير وجذّاب بأسلوب الصفحة.

قواعد صارمة:
- استعمل فقط المعلومات الواردة في الخبر. لا تخترع نتائج أو أسماء أو أرقامًا أو تواريخ أو أحداثًا.
- ممنوع منعًا باتًّا إضافة أي معلومة ليست في النص الأصلي (لا نتيجة، لا تقييم، لا مكان، لا تاريخ). إن لم تُذكر، لا تكتبها.
- إن كان الخبر غامضًا أو ناقصًا، اكتب فقط ما تأكّدتَ منه ولو كان قصيرًا.
- العربية الفصحى المبسّطة، نبرة حماسية محترمة، وتجنّب أي محتوى مخالف للقيم.
- اهتمّ بإبراز اللاعبين العرب إن ورد ذكرهم.

أسماء الأعلام (مهم جدًا):
- اكتب أسماء اللاعبين والبطولات والافتتاحات بحروفها اللاتينية (الإنجليزية) كما وردت في المصدر تمامًا:
  Magnus Carlsen، Alireza Firouzja، Arjun Erigaisi، Nihal Sarin … ولا تنقلها صوتيًا إلى العربية إطلاقًا.
- المصطلحات الإنجليزية تبقى لاتينية أيضًا: Blitz، Rapid، Bullet، Bracket، Arena …
- ادمج الاسم اللاتيني داخل الجملة العربية مباشرة، مثال: «تأهّل Firouzja إلى النهائي».

جودة اللغة (مهم):
- العربية واللاتينية فقط. ممنوع منعًا باتًّا أي حروف صينية أو يابانية أو كورية أو سيريلية (汉字 / カ / и) — لا تستعملها إطلاقًا ولو حرفًا واحدًا.
- عربية سليمة ومدقّقة إملائيًا، بلا كلمات مبتورة أو غريبة. راجع النص قبل إخراجه.

أعد ردّك بصيغة JSON فقط (بدون أي نص خارجها) بالمفاتيح التالية:
{
  "title": "عنوان قصير قوي من 3 إلى 6 كلمات",
  "body": "سطران إلى أربعة أسطر تشرح الخبر، تنتهي بسؤال تفاعلي للمتابعين",
  "hashtags": ["وسم1", "وسم2", "وسم3"],
  "event": "اسم البطولة/الحدث بحروفه اللاتينية كما في المصدر (مثل: Norway Chess 2026). إن لم يُذكر حدث، فاسم المكان أو الموضوع باختصار شديد (كلمتان كحد أقصى). لا تترك الحقل فارغًا.",
  "category": "صنّف الخبر بكلمة واحدة من: result (نتيجة/فوز) | tournament (بطولة/إعلان) | historical (تاريخ/ذكريات) | interview (حوار) | statement (تصريح/تصريحات) | obituary (وفاة/تأبين) | opening (افتتاحات/تحليل) | general (غير ذلك)"
}"""


SYSTEM_EN = """You are the editor of the "Tawwat Chess" Facebook page, covering Arab and world chess.
Your task: turn a chess news item into a short, engaging English post in the page's voice.

Strict rules:
- Use ONLY the information in the article. Never invent results, names, numbers, dates, or events.
- If a detail is not confirmed in the text, do not mention it at all.
- Use ONLY Latin letters. Absolutely no Chinese/Japanese/Korean/Cyrillic characters.
- Clear, lively but respectful tone. Keep player and tournament names in their original spelling.
- Highlight Arab players if they are mentioned.

Reply with JSON ONLY (no text outside it), with these keys:
{
  "title": "a short punchy headline of 3 to 6 words",
  "body": "two to four lines explaining the news, ending with an engaging question to followers",
  "hashtags": ["tag1", "tag2", "tag3"],
  "event": "the tournament/event name in its original spelling (e.g. Norway Chess 2026). If no event is named, a very short place or topic (two words max). Never leave it empty.",
  "category": "classify in one word: result | tournament | historical | interview | statement | obituary | opening | general"
}"""


def _complete(system, user):
    """ينفّذ الطلب على المزوّد المفعّل ويعيد نص الرد. يرمي خطأً واضحًا إن لم يُضبط أي مزوّد."""
    global _openai_client, _anthropic_client

    if config.LLM_API_BASE:  # ===== مزوّد متوافق مع OpenAI (مجاني عادةً) =====
        if _openai_client is None:
            from openai import OpenAI
            _openai_client = OpenAI(base_url=config.LLM_API_BASE, api_key=config.LLM_API_KEY)
        resp = _openai_client.chat.completions.create(
            model=config.LLM_MODEL,
            max_tokens=800,
            temperature=0.7,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content

    if config.ANTHROPIC_API_KEY:  # ===== Claude مباشرة (مدفوع) =====
        if _anthropic_client is None:
            from anthropic import Anthropic
            _anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = _anthropic_client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    raise RuntimeError("خدمة إعادة الصياغة غير مضبوطة: املأ LLM_API_BASE/LLM_API_KEY/LLM_MODEL "
                       "أو ANTHROPIC_API_KEY في ملف .env")


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _names_hint(article, lang):
    """تلميح بأبرز اللاعبين المذكورين مع فرض التهجئة اللاتينية وإبراز العرب."""
    arab = article.get("arab_hits") or []
    world = article.get("world_hits") or []
    names = arab + [w for w in world if w not in arab]
    hint = ""
    if lang == "ar":
        if names:
            hint += ("\n\nاكتب أسماء هؤلاء اللاعبين بحروفها اللاتينية بالضبط كما هنا "
                     "(لا تنقلها للعربية): " + " ، ".join(names) + ".")
        if arab:
            hint += ("\nهذا الخبر يخصّ لاعبًا/لاعبين عربًا: " + " ، ".join(arab)
                     + " — أبرِزهم في العنوان والنص.")
    else:
        if names:
            hint += "\n\nSpell these player names exactly: " + ", ".join(names) + "."
        if arab:
            hint += "\nThis news features Arab player(s): " + ", ".join(arab) + " — highlight them."
    return hint


def _generate(article, system, lang):
    if lang == "ar":
        user = (f"المصدر: {article['source']}\n"
                f"العنوان: {article['title']}\n"
                f"الملخص: {article['summary']}\n"
                f"الرابط: {article['link']}")
    else:
        user = (f"Source: {article['source']}\n"
                f"Title: {article['title']}\n"
                f"Summary: {article['summary']}\n"
                f"Link: {article['link']}")
    user += _names_hint(article, lang)
    data = _extract_json(_complete(system, user))
    data.setdefault("title", article["title"][:60])
    data.setdefault("body", "")
    data.setdefault("hashtags", [])
    # تنقية من الحروف الصينية/السيريلية (وقاية من أخطاء النموذج)
    data["title"] = _sanitize(data["title"]) or article["title"][:60]
    data["body"] = _sanitize(data["body"])
    data["event"] = _sanitize((data.get("event") or "").strip())
    data["category"] = (data.get("category") or "general").strip().lower()
    if isinstance(data["hashtags"], str):
        data["hashtags"] = [data["hashtags"]]
    data["hashtags"] = [_sanitize(str(h)) for h in data["hashtags"] if _sanitize(str(h))]
    return data


def to_arabic(article):
    """يعيد dict فيه title و body و hashtags (بالعربية)."""
    return _generate(article, SYSTEM, "ar")


def to_english(article):
    """Return dict with title, body, hashtags (in English)."""
    return _generate(article, SYSTEM_EN, "en")


def build_caption(article, data, lang="ar"):
    """تركيب نص المنشور النهائي لفيسبوك (العنوان + التفاصيل + الوسوم + المصدر)."""
    hashtags = list(data.get("hashtags", []))
    # وسم خاص لإبراز اللاعبين العرب
    if article.get("arab_hits"):
        hashtags.append("لاعبون_عرب" if lang == "ar" else "ArabPlayers")
    tags = " ".join("#" + str(h).lstrip("#").replace(" ", "_") for h in hashtags)
    parts = [data["title"].strip()]
    if data.get("body"):
        parts.append(data["body"].strip())
    if tags:
        parts.append(tags)
    parts.append((f"🔗 المصدر: {article['source']}") if lang == "ar"
                 else (f"🔗 Source: {article['source']}"))
    return "\n\n".join(parts)
