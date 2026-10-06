"""Tell job offers apart from everything else posted in the groups (chat, people looking for work,
parcels, flights, sales, courses and other services).

Rule-based and transparent: the post body (forwarding header removed) is cleaned and transliterated to
Latin, then scored. Hiring phrases ("ish bor", "5 kishiga", "ishchi kerak", "требуются", "구인"), pay,
working terms (shifts, days, meals, housing) and job types add evidence; signs of another kind of post
take it away. Typical use:

    is_job_post(text)          # True for a job offer
    classify_post(text)        # "job_offer" | "job_seeker" | "cargo" | "travel" | "sale" | "service" | "chat"
"""

import re
from functools import lru_cache

from src.utils.post_parsing import post_body
from src.utils.salary import main_salary
from src.utils.text_cleaning import clean_text

KINDS = ("job_offer", "job_seeker", "cargo", "travel", "sale", "service", "chat")
JOB_OFFER = "job_offer"
THRESHOLD = 3.0

APOSTROPHES = re.compile(r"[ʻʼ’‘`'´]")
CLOCK = re.compile(r"(?<!\d)\d{1,2}[:.]\d{2}(?!\d)")


def _words(*patterns: str) -> re.Pattern:
    return re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)")


# Someone is hiring.
ROLES = (
    r"kishi|kshi|kishii|kiwi|kish|kiwii|odam|ishchi|iwchi|ishchilar|xodim|hodim|ayol|ayollar|erkak|erkaklar|qiz|qizlar|yigit|yigitlar"
    r"|bola|bolalar|nafar|oshpaz|povar|haydovchi|voditel|shofyor|svarshik|payvandchi|usta|ustalar|sotuvchi|kassir|ofitsiant|farrosh"
    r"|operator|mexanik|elektrik|santexnik|malyar|kafelchi|montajchi|yordamchi|qorovul|enaga|sidelka|massajchi|tikuvchi"
)
NUMBER = r"(?:\d+|bir|ikki|uch|tort|besh|olti|yetti|etti|sakkiz|toqqiz|on|bitta|ikkita|uchta|tortta|beshta)"
HIRING = _words(
    r"[ie][sw]h?\s*bor", r"ishlar\s+bor", r"iwlar\s+bor", r"\w+\s+[ie][sw]h?i\s+bor", r"ish\s+(?:taklif|beramiz|beriladi)", r"ishga\s+(?:olamiz|olinadi|chaqir\w*|taklif\w*|kerak\w*)",
    NUMBER + r"?\s*(?:ta\s*)?(?:" + ROLES + r")(?:ga|lar|larga|ni)?\s+(?:yana\s+)?(?:kerak|kere|kerek|kk|zarur|olamiz|olinadi)",
    # "5 kishiga", "2 ta ayolga": a headcount addressed to people (a bare "1 kishi bor" is someone available)
    NUMBER + r"\s*(?:ta\s*)?(?:\w+\s+)?(?:kishi|kshi|kishii|kish|kiwi|odam|ishchi|iwchi|nafar|ayol|erkak|qiz|yigit)(?:i|lar)?(?:ga|larga)",
    r"vakans\w*", r"trebu\w*", r"rabotnik\w*", r"rabota\s+est", r"est\s+rabota",
    r"nu(?:zh|j)n\w*\s+(?:\d+\s*)?(?:rabotn|lyud|lud|muzh|muj|zhensh|jensh|devush|parn|sotrudn|chelovek)\w*",
    r"doimiy\s+ish\w*", r"postoyann\w*", r"arbayt\s+bor", r"albayt\s+bor",
    r"[ie][sw]h?\s+(?:o?rni|urni|urini|orini)\w*\s+bor", r"dlya\s+rabot\w*", r"na\s+rabotu", r"zarabotn\w*",
)
HIRING_KO = re.compile(r"구인|모집|채용|알바|아르바이트|일당|시급|근무자|직원")
SEEKER_KO = re.compile(r"구직|일자리\s*구합니다|일\s*구합니다|일자리\s*찾")

# Pay and working terms.
PAY_WORDS = _words(
    r"soatiga", r"soatga", r"soatlik", r"kunlik", r"kuniga", r"oylik", r"maosh\w*", r"ish\s+haqq?i", r"zarplat\w*", r"oplat\w*",
    r"chanob", r"chanop", r"won", r"von", r"vonn", r"ming\s+won", r"min\s+won", r"tisyach\w*",
)
TERMS = _words(
    r"dushanba\w*", r"seshanba\w*", r"chorshanba\w*", r"payshanba\w*", r"juma\w*", r"shanba\w*", r"yakshanba\w*",
    r"smena\w*", r"obed\w*", r"tushlik", r"yotoq\w*", r"jilyo", r"ish\s+vaqti", r"soat\s*\d+\w*", r"\d+\s*soat\w*",
    r"manzil", r"adres\w*", r"ertadan", r"ertaga", r"srochno", r"srochniy", r"boshlanadi", r"ish\s+turi", r"ish\s+joyi",
    r"uy\s+beriladi", r"kvartira\s+beriladi", r"benzin\w*\s+(?:puli|beriladi)", r"transport\w*", r"avtobus\w*", r"viza\w*",
)
JOB_TYPES = _words(
    r"zavod\w*", r"fabrika\w*", r"tekpe\w*", r"taekpe\w*", r"sklad\w*", r"ombor\w*", r"uborka\w*", r"tozalash\w*", r"qurilish\w*",
    r"stroyk\w*", r"oshxona\w*", r"restoran\w*", r"povar\w*", r"ofitsiant\w*", r"kema\w*", r"baliq\w*", r"dala\w*", r"ferma\w*",
    r"teplits\w*", r"issiqxona\w*", r"kuryer\w*", r"dostavk\w*", r"karopka\w*", r"korobk\w*", r"pochtaga", r"motel\w*", r"mehmonxona\w*",
)
JOB_TYPES_KO = re.compile(r"공장|식당|주방|청소|건설|물류|창고|택배|농장|배달|조선|어선")

# Other kinds of posts.
SEEKER = _words(
    r"[ie][sw]h?\s+bormi", r"ishlar\s+bormi", r"[ie][sw]h?\s+(?:bolsa|bosa|bolse)", r"[ie][sw]h?\s+kerak\w*", r"menga\s+ish", r"bizga\s+ish",
    r"ish\s+(?:qidir|izla)\w*", r"ish\s+topib\s+ber\w*", r"rabot[uy]\s+ishu", r"ishu\s+rabot\w*", r"ish\s+yoqmi",
    r"kerak\s+bo?p\s+qolsa", r"kerak\s+bolib\s+qolsa",
)
CARGO = _words(
    r"posilka\w*", r"posilk\w*", r"kargo\w*", r"cargo", r"bagaj\w*", r"yuk\s+(?:olamiz|olaman|bolsa|bosa|olib)\w*",
    r"pochta\s+(?:bolsa|bosa|olib|olamiz|olaman)\w*", r"olib\s+(?:ketaman|ketamiz|boraman|boramiz|kelaman|kelamiz)",
    r"jonatamiz", r"jonataman", r"zakaz\w*\s+olamiz",
)
TRAVEL = _words(
    r"avia\w*", r"bilet\w*", r"reys\w*", r"aviakompaniya\w*", r"poputi", r"poputchik\w*", r"poputno",
    r"uchaman", r"uchamiz", r"uchiladi", r"uchamz", r"samolyot\w*", r"ketaman",
    r"(?:moshina|mashina|moshna|mashna)\w*\s+(?:\d+\s*)?(?:ta\s*)?(?:kishi\w*\s+)?joy",  # seats free in a car
    r"kishi\w*\s+joy\s+bor", r"ketuvchilar\w*", r"borib\s+qaytamiz",
)
SALE = _words(
    r"sotiladi", r"sotaman", r"sotamiz", r"sotuvda", r"prodayu", r"prodaets\w*", r"prodam", r"arzon\s+narx\w*",
    r"ijaraga", r"arenda\w*", r"sotib\s+olaman", r"sotib\s+olamiz",
    # phone numbers and tariffs
    r"sim\s*karta\w*", r"tarif\w*",
    # rooms and flats for rent or to share
    r"one\s*room", r"oneroom", r"wolse\w*", r"volse\w*", r"jonse\w*", r"depozit\w*", r"sheriklikka", r"kvartira\s+(?:sotiladi|ijaraga|bor)",
)
# A car ad names at least two of these (fuel alone is a job perk: "benzin puli beriladi").
CAR = _words(
    r"yili", r"yurgani", r"probeg\w*", r"balon\w*", r"benzin\w*", r"dizel\w*", r"lpg", r"(?:avtomat|mexanika)\s+(?:karopka|korobka)",
    r"karobka\w*", r"rasxod\w*", r"tonirovka\w*", r"kuzov\w*",
)
SERVICE = _words(
    r"kurs(?:lar|imiz|i)?", r"dars(?:lar|larimiz|i)?", r"ielts", r"repetitor\w*", r"oqituvchi\w*",
    r"pul\s+otkaz\w*", r"pul\s+(?:otkazma|jonat)\w*", r"valyuta\w*", r"dollar\s+kurs\w*", r"kredit\w*", r"strahovk\w*",
    r"sugurta\w*", r"zaym\w*", r"zaim\w*", r"pomog\w*\s+s\s+deng\w*", r"viza\s+(?:xizmat|ochib|qilib)\w*", r"taks?[iy]\s+xizmat\w*", r"taxi\s+xizmat\w*", r"hujjat\w*\s+(?:tayyorla|qilib\s+ber)\w*", r"tarjima\w*\s+xizmat\w*",
)
OTHER_KINDS = (("cargo", CARGO), ("travel", TRAVEL), ("sale", SALE), ("service", SERVICE))


def normalize(text: str) -> str:
    """The post body, lower-cased, in Latin letters, without emoji and apostrophes; phones masked."""
    return APOSTROPHES.sub("", clean_text(post_body(text), mask_phones=True, mask_numbers=False))


@lru_cache(maxsize=4096)
def _classify(text: str) -> tuple[str, float]:
    body = post_body(text)
    words = normalize(text)
    if len(words.strip()) < 5:
        return "chat", 0.0
    hiring = bool(HIRING.search(words) or HIRING_KO.search(body))
    pay = main_salary(body) is not None
    pay_words = bool(PAY_WORDS.search(words))
    terms = len(set(m.group(0) for m in TERMS.finditer(words)))
    job_type = bool(JOB_TYPES.search(words) or JOB_TYPES_KO.search(body))
    contact = "PHONE" in words or "lichka" in words or "shaxsiy" in words

    details = pay or job_type or terms >= 2
    score = 3.0 * hiring + 2.0 * pay + 1.0 * pay_words + min(terms, 3) * 0.75 + 1.0 * job_type + 0.5 * contact
    seeker = bool(SEEKER.search(words) or SEEKER_KO.search(body))
    others = [kind for kind, pattern in OTHER_KINDS if pattern.search(words)]
    if len({m.group(0) for m in CAR.finditer(words)}) >= 2:
        others.append("sale")
    score -= 4.0 * len(others) + (2.0 if seeker and not hiring else 0.0)

    if seeker and not details:  # "2 kishiga ish bormi?", "ish bolsa bir kishi bor"
        return "job_seeker", score
    rich_offer = hiring and pay and (job_type or terms >= 2)
    # A shift notice without a hiring phrase: "Seshanba 25ta. Manzil: ... 20:00dan boshlanadi"
    schedule_notice = terms >= 3 and bool(CLOCK.search(body)) and not others and not seeker
    offer_shaped = hiring or (pay and (job_type or terms >= 2))
    if rich_offer or schedule_notice or (offer_shaped and score >= THRESHOLD):
        return JOB_OFFER, score
    if seeker:
        return "job_seeker", score
    if others:
        return others[0], score
    return "chat", score


def classify_post(text: str) -> str:
    """One of KINDS for a Telegram message text (forwarded posts are judged by their job text)."""
    return _classify(text if isinstance(text, str) else "")[0]


def job_score(text: str) -> float:
    """Evidence that the text is a job offer (THRESHOLD and up, with a hiring phrase or pay, counts)."""
    return _classify(text if isinstance(text, str) else "")[1]


def is_job_post(text: str) -> bool:
    """True when the message is a job offer."""
    return classify_post(text) == JOB_OFFER
