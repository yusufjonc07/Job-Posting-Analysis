"""Resolve a job post's province and city from Korean addresses, falling back to its group."""

import csv
import re
import tempfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

from src.utils.post_parsing import post_body
from src.utils.transliteration import cyrillic_to_latin

# Province names match the `province` column of data/telegram_groups.csv.
PROVINCE_ALIASES: dict[str, tuple[str, ...]] = {
    "Seoul": ("서울특별시", "서울시", "서울"),
    "Busan": ("부산광역시", "부산시", "부산"),
    "Daegu": ("대구광역시", "대구시", "대구"),
    "Incheon": ("인천광역시", "인천시", "인천"),
    "Gwangju": ("광주광역시",),
    "Daejeon": ("대전광역시", "대전시", "대전"),
    "Ulsan": ("울산광역시", "울산시", "울산"),
    "Sejong": ("세종특별자치시", "세종시", "세종"),
    "Gyeonggi-do": ("경기도", "경기"),
    "Gangwon-do": ("강원특별자치도", "강원도", "강원"),
    "Chungcheongbuk-do": ("충청북도", "충북"),
    "Chungcheongnam-do": ("충청남도", "충남"),
    "Jeollabuk-do": ("전북특별자치도", "전라북도", "전북"),
    "Jeollanam-do": ("전라남도", "전남"),
    "Gyeongsangbuk-do": ("경상북도", "경북"),
    "Gyeongsangnam-do": ("경상남도", "경남"),
    "Jeju-do": ("제주특별자치도", "제주도"),
}
METROPOLITAN = {"Seoul", "Busan", "Daegu", "Incheon", "Gwangju", "Daejeon", "Ulsan", "Sejong"}

# Korean si/gun name (without 시/군 suffix) -> English city name, per province.
CITIES: dict[str, dict[str, str]] = {
    "Gyeonggi-do": {
        "수원": "Suwon", "성남": "Seongnam", "고양": "Goyang", "용인": "Yongin", "부천": "Bucheon",
        "안산": "Ansan", "안양": "Anyang", "남양주": "Namyangju", "화성": "Hwaseong", "평택": "Pyeongtaek",
        "의정부": "Uijeongbu", "시흥": "Siheung", "파주": "Paju", "김포": "Gimpo", "광명": "Gwangmyeong",
        "광주": "Gwangju", "군포": "Gunpo", "하남": "Hanam", "오산": "Osan", "이천": "Icheon",
        "안성": "Anseong", "의왕": "Uiwang", "양주": "Yangju", "구리": "Guri", "포천": "Pocheon",
        "동두천": "Dongducheon", "과천": "Gwacheon", "여주": "Yeoju", "양평": "Yangpyeong",
        "가평": "Gapyeong", "연천": "Yeoncheon",
    },
    "Gangwon-do": {
        "춘천": "Chuncheon", "원주": "Wonju", "강릉": "Gangneung", "동해": "Donghae", "태백": "Taebaek",
        "속초": "Sokcho", "삼척": "Samcheok", "홍천": "Hongcheon", "횡성": "Hoengseong", "영월": "Yeongwol",
        "평창": "Pyeongchang", "정선": "Jeongseon", "철원": "Cheorwon", "화천": "Hwacheon", "양구": "Yanggu",
        "인제": "Inje", "고성": "Goseong", "양양": "Yangyang",
    },
    "Chungcheongbuk-do": {
        "청주": "Cheongju", "충주": "Chungju", "제천": "Jecheon", "보은": "Boeun", "옥천": "Okcheon",
        "영동": "Yeongdong", "증평": "Jeungpyeong", "진천": "Jincheon", "괴산": "Goesan", "음성": "Eumseong",
        "단양": "Danyang",
    },
    "Chungcheongnam-do": {
        "천안": "Cheonan", "공주": "Gongju", "보령": "Boryeong", "아산": "Asan", "서산": "Seosan",
        "논산": "Nonsan", "계룡": "Gyeryong", "당진": "Dangjin", "금산": "Geumsan", "부여": "Buyeo",
        "서천": "Seocheon", "청양": "Cheongyang", "홍성": "Hongseong", "예산": "Yesan", "태안": "Taean",
    },
    "Jeollabuk-do": {
        "전주": "Jeonju", "군산": "Gunsan", "익산": "Iksan", "정읍": "Jeongeup", "남원": "Namwon",
        "김제": "Gimje", "완주": "Wanju", "진안": "Jinan", "무주": "Muju", "장수": "Jangsu", "임실": "Imsil",
        "순창": "Sunchang", "고창": "Gochang", "부안": "Buan",
    },
    "Jeollanam-do": {
        "목포": "Mokpo", "여수": "Yeosu", "순천": "Suncheon", "나주": "Naju", "광양": "Gwangyang",
        "담양": "Damyang", "곡성": "Gokseong", "구례": "Gurye", "고흥": "Goheung", "보성": "Boseong",
        "화순": "Hwasun", "장흥": "Jangheung", "강진": "Gangjin", "해남": "Haenam", "영암": "Yeongam",
        "무안": "Muan", "함평": "Hampyeong", "영광": "Yeonggwang", "장성": "Jangseong", "완도": "Wando",
        "진도": "Jindo", "신안": "Sinan",
    },
    "Gyeongsangbuk-do": {
        "포항": "Pohang", "경주": "Gyeongju", "김천": "Gimcheon", "안동": "Andong", "구미": "Gumi",
        "영주": "Yeongju", "영천": "Yeongcheon", "상주": "Sangju", "문경": "Mungyeong", "경산": "Gyeongsan",
        "의성": "Uiseong", "청송": "Cheongsong", "영양": "Yeongyang", "영덕": "Yeongdeok", "청도": "Cheongdo",
        "고령": "Goryeong", "성주": "Seongju", "칠곡": "Chilgok", "예천": "Yecheon", "봉화": "Bonghwa",
        "울진": "Uljin", "울릉": "Ulleung",
    },
    "Gyeongsangnam-do": {
        "창원": "Changwon", "진주": "Jinju", "통영": "Tongyeong", "사천": "Sacheon", "김해": "Gimhae",
        "밀양": "Miryang", "거제": "Geoje", "양산": "Yangsan", "의령": "Uiryeong", "함안": "Haman",
        "창녕": "Changnyeong", "고성": "Goseong", "남해": "Namhae", "하동": "Hadong", "산청": "Sancheong",
        "함양": "Hamyang", "거창": "Geochang", "합천": "Hapcheon",
    },
    "Jeju-do": {"제주": "Jeju", "서귀포": "Seogwipo"},
}

# Districts (구/군) whose name is unique nationwide -> (province, city).
DISTRICTS: dict[str, tuple[str, str]] = {
    **{name: ("Seoul", "Seoul") for name in (
        "종로", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉", "노원", "은평", "서대문",
        "마포", "양천", "구로", "금천", "영등포", "동작", "관악", "서초", "강남", "송파", "강동",
    )},
    **{name: ("Busan", "Busan") for name in (
        "해운대", "사하", "금정", "연제", "수영", "사상", "부산진", "영도", "기장",
    )},
    **{name: ("Daegu", "Daegu") for name in ("수성", "달서", "달성", "군위")},
    **{name: ("Incheon", "Incheon") for name in ("미추홀", "연수", "남동", "부평", "계양", "강화", "옹진")},
    "광산": ("Gwangju", "Gwangju"),
    "유성": ("Daejeon", "Daejeon"), "대덕": ("Daejeon", "Daejeon"),
    "울주": ("Ulsan", "Ulsan"),
    **{name: ("Gyeonggi-do", "Suwon") for name in ("장안", "권선", "팔달", "영통")},
    **{name: ("Gyeonggi-do", "Seongnam") for name in ("수정", "중원", "분당")},
    **{name: ("Gyeonggi-do", "Goyang") for name in ("덕양", "일산동", "일산서")},
    **{name: ("Gyeonggi-do", "Yongin") for name in ("처인", "기흥", "수지")},
    **{name: ("Gyeonggi-do", "Ansan") for name in ("상록", "단원")},
    **{name: ("Gyeonggi-do", "Anyang") for name in ("만안", "동안")},
    **{name: ("Chungcheongnam-do", "Cheonan") for name in ("동남", "서북")},
    **{name: ("Chungcheongbuk-do", "Cheongju") for name in ("상당", "서원", "흥덕", "청원")},
    **{name: ("Jeollabuk-do", "Jeonju") for name in ("완산", "덕진")},
    **{name: ("Gyeongsangnam-do", "Changwon") for name in ("의창", "성산", "마산합포", "마산회원", "진해")},
}

NOT_HANGUL_BEFORE = r"(?<![가-힣])"
PROVINCE_PATTERN = re.compile(
    NOT_HANGUL_BEFORE + "(" + "|".join(sorted(
        (alias for aliases in PROVINCE_ALIASES.values() for alias in aliases), key=len, reverse=True
    )) + ")"
)
PROVINCE_BY_ALIAS = {alias: province for province, aliases in PROVINCE_ALIASES.items() for alias in aliases}
# A city needs its 시/군 suffix, unless it directly follows a province name ("경기 화성", "충남 천안시").
CITY_NAMES = sorted({name for cities in CITIES.values() for name in cities}, key=len, reverse=True)
CITY_PATTERN = re.compile(NOT_HANGUL_BEFORE + "(" + "|".join(CITY_NAMES) + ")(시|군)(?!간)")
PROVINCE_CITY_PATTERN = re.compile(PROVINCE_PATTERN.pattern + r"\s*(" + "|".join(CITY_NAMES) + ")")
DISTRICT_PATTERN = re.compile(
    NOT_HANGUL_BEFORE + "(" + "|".join(sorted(DISTRICTS, key=len, reverse=True)) + ")(구|군)"
)


def provinces_of_city(name: str) -> list[str]:
    return [province for province, cities in CITIES.items() if name in cities]


def address_location(text: str) -> tuple[str, str] | None:
    """Return (province, city) from the first Korean address found in a post, or None."""
    # Only the job text: the header's `Guruh:` line holds the group title, not the job address.
    body = post_body(text)
    mentioned = [PROVINCE_BY_ALIAS[match.group(1)] for match in PROVINCE_PATTERN.finditer(body)]

    candidates: list[tuple[int, str, str]] = []
    for match in PROVINCE_CITY_PATTERN.finditer(body):
        province = PROVINCE_BY_ALIAS[match.group(1)]
        if match.group(2) in CITIES.get(province, {}):
            candidates.append((match.start(), province, CITIES[province][match.group(2)]))
    for match in CITY_PATTERN.finditer(body):
        provinces = provinces_of_city(match.group(1))
        if match.group(1) == "광주" and match.group(2) == "시" and "Gyeonggi-do" not in mentioned:
            continue  # "광주시" alone is ambiguous with Gwangju Metropolitan City
        if len(provinces) > 1:  # e.g. 고성군: use the province named in the post to disambiguate
            provinces = [province for province in provinces if province in mentioned]
        if len(provinces) == 1:
            candidates.append((match.start(), provinces[0], CITIES[provinces[0]][match.group(1)]))
    for match in DISTRICT_PATTERN.finditer(body):
        candidates.append((match.start(), *DISTRICTS[match.group(1)]))
    for match in PROVINCE_PATTERN.finditer(body):
        province = PROVINCE_BY_ALIAS[match.group(1)]
        if province in METROPOLITAN:
            candidates.append((match.start(), province, province))
        elif match.group(1).endswith("도"):  # full province name with no recognizable city
            candidates.append((match.start() + len(body), province, ""))  # rank below any city match

    if not candidates:
        return None
    _, province, city = min(candidates)
    return province, city


# ---------------------------------------------------------------------------
# Place names written in Latin/Cyrillic (Uzbek, Russian, English spellings)
# ---------------------------------------------------------------------------

# Spellings that the phonetic key below does not merge with the official romanization.
LATIN_ALIASES: dict[str, tuple[str, str]] = {
    "seul": ("Seoul", "Seoul"),
    "pentek": ("Gyeonggi-do", "Pyeongtaek"),
    "chinchon": ("Chungcheongbuk-do", "Jincheon"), "chincheon": ("Chungcheongbuk-do", "Jincheon"),
    # Well-known towns and industrial areas, mapped to the city they belong to.
    "sinchang": ("Chungcheongnam-do", "Asan"), "singchan": ("Chungcheongnam-do", "Asan"),
    "noksan": ("Busan", "Busan"),
    "seonghwan": ("Chungcheongnam-do", "Cheonan"), "songhwan": ("Chungcheongnam-do", "Cheonan"),
    "waegwan": ("Gyeongsangbuk-do", "Chilgok"), "vegvan": ("Gyeongsangbuk-do", "Chilgok"),
    "bupyeong": ("Incheon", "Incheon"), "pupyong": ("Incheon", "Incheon"),
    "chinyong": ("Gyeongsangnam-do", "Gimhae"), "jinyong": ("Gyeongsangnam-do", "Gimhae"),
    "sixin": ("Gyeonggi-do", "Siheung"), "shixin": ("Gyeonggi-do", "Siheung"),
}
LATIN_PROVINCES: dict[str, str] = {
    "gyeonggi": "Gyeonggi-do", "gyeonggido": "Gyeonggi-do", "kyongido": "Gyeonggi-do", "kiyongido": "Gyeonggi-do",
    "chungnam": "Chungcheongnam-do", "chungcheongnam": "Chungcheongnam-do",
    "chungbuk": "Chungcheongbuk-do", "chungcheongbuk": "Chungcheongbuk-do",
    "jeonnam": "Jeollanam-do", "chonnam": "Jeollanam-do", "jeollanam": "Jeollanam-do",
    "jeonbuk": "Jeollabuk-do", "chonbuk": "Jeollabuk-do", "jeollabuk": "Jeollabuk-do",
    "gyeongnam": "Gyeongsangnam-do", "gyeongsangnam": "Gyeongsangnam-do",
    "gyeongbuk": "Gyeongsangbuk-do", "gyeongsangbuk": "Gyeongsangbuk-do",
    "gangwon": "Gangwon-do", "gangwondo": "Gangwon-do",
    **{name + "do": province for name, province in (
        ("chungcheongnam", "Chungcheongnam-do"), ("chungcheongbuk", "Chungcheongbuk-do"),
        ("jeollanam", "Jeollanam-do"), ("jeollabuk", "Jeollabuk-do"),
        ("gyeongsangnam", "Gyeongsangnam-do"), ("gyeongsangbuk", "Gyeongsangbuk-do"),
    )},
}
# First word of a two-word province name ("kyongsang buk do", "chungcheong nam do"); never a city by itself.
REGION_PREFIXES: dict[str, dict[str, str]] = {
    "kyonsan": {"puk": "Gyeongsangbuk-do", "nam": "Gyeongsangnam-do"},
    "chunchon": {"puk": "Chungcheongbuk-do", "nam": "Chungcheongnam-do"},
    "jola": {"puk": "Jeollabuk-do", "nam": "Jeollanam-do"},
    "chola": {"puk": "Jeollabuk-do", "nam": "Jeollanam-do"},
}
REGION_WORDS = {"kyongsang", "gyeongsang", "chungcheong", "chungchong", "chungchxong", "jeolla", "cholla"}
# Everyday words within one edit of a place name; never fuzzy-matched (prefix match, so endings are covered).
FUZZY_STOPWORDS = (
    "qachon", "kundan", "shuncha", "bojxona", "bojhona", "kochada", "kochaga", "kochat", "tanlang",
    "chonsu", "chongsu", "dongwon", "yakshan",
)
# Uzbek case/derivation endings (plus Russian -e/-a/-u), longest first: inchondan, teguga, chonandagila.
ENDINGS = tuple(sorted((
    "dagilarga", "dagilar", "dagila", "dagini", "dagi", "daman", "gacha", "lardan", "larga", "liklar", "likka", "lik",
    "ning", "dan", "tan", "dir", "da", "ta", "ga", "ka", "qa", "ni", "e", "a", "u",
), key=len, reverse=True))
# Short names that are also everyday words ("oson" = easy, "asan"), so they need an ending: osanda, asanga.
NEEDS_ENDING = {"osan", "asan", "guri", "muan", "buan", "inje", "naju", "jinan", "sinan", "jindo", "imsil"}
MIN_FUZZY_LENGTH = 6
TOKEN_PATTERN = re.compile(r"[a-z]+")


def phonetic_key(word: str) -> str:
    """Merge spellings of the same Korean sound: tegu/daegu/degu/taegu, pyontek/pyeongtaek, xvasong/hwaseong.

    The y of yeo/yo is kept so that Gyeongju (kyonju) and Gongju (konju) stay apart.
    """
    key = cyrillic_to_latin(word).lower().replace("'", "")
    for old, new in (("yeo", "yo"), ("eo", "o"), ("ae", "e"), ("eu", "u"), ("kh", "h"), ("ng", "n"),
                     ("g", "k"), ("d", "t"), ("b", "p"), ("w", "v"), ("x", "h"), ("sh", "s")):
        key = key.replace(old, new)
    return re.sub(r"(.)\1+", r"\1", key)  # collapse doubled letters: inchxon -> inchhon -> inchon


def _build_latin_gazetteer() -> dict[str, set[tuple[str, str]]]:
    """Phonetic key -> every (province, city) it can mean; more than one entry means ambiguous."""
    gazetteer: dict[str, set[tuple[str, str]]] = {}
    places = [(province, city) for province, cities in CITIES.items() for city in cities.values()]
    places += [(metro, metro) for metro in METROPOLITAN]
    places += [location for location in DISTRICTS.values()]
    for province, city in places:
        gazetteer.setdefault(phonetic_key(city), set()).add((province, city))
    for alias, location in LATIN_ALIASES.items():
        gazetteer.setdefault(phonetic_key(alias), set()).add(location)
    return gazetteer


LATIN_GAZETTEER = _build_latin_gazetteer()
LATIN_PROVINCE_KEYS = {phonetic_key(alias): province for alias, province in LATIN_PROVINCES.items()}
FUZZY_KEYS = [key for key in LATIN_GAZETTEER if len(key) >= MIN_FUZZY_LENGTH]


def _fuzzy_key(key: str) -> str | None:
    """Closest gazetteer key within 1 edit (2 for long names), only if no other key is as close."""
    if len(key) < MIN_FUZZY_LENGTH:
        return None
    max_distance = 1 if len(key) < 9 else 2
    matches = process.extract(key, FUZZY_KEYS, scorer=Levenshtein.distance, score_cutoff=max_distance, limit=2)
    if not matches or (len(matches) > 1 and matches[1][1] == matches[0][1]):
        return None
    return matches[0][0]


@lru_cache(maxsize=500_000)
def match_place_word(word: str) -> tuple[frozenset, str] | None:
    """Resolve one lower-case Latin word to its possible places and how it matched.

    Steps: exact phonetic key ('exact') -> key of the word without an Uzbek/Russian ending ('ending')
    -> closest key within 1-2 edits, long names only ('fuzzy'). Endings are removed before building
    the key, because merging "ng" would otherwise join name and ending (osan+ga -> "osana").
    """
    key = phonetic_key(word)
    if key in LATIN_GAZETTEER and key not in NEEDS_ENDING:
        return frozenset(LATIN_GAZETTEER[key]), "exact"
    stems = []
    for ending in ENDINGS:
        stem = word[: -len(ending)]
        if not word.endswith(ending) or len(stem) < 4 or (len(ending) == 1 and len(stem) < 5):
            continue
        stem_key = phonetic_key(stem)
        if stem_key in LATIN_GAZETTEER and (len(ending) > 1 or stem_key not in NEEDS_ENDING):
            return frozenset(LATIN_GAZETTEER[stem_key]), "ending"
        stems.append(stem_key)
    if word.startswith(FUZZY_STOPWORDS):
        return None
    for candidate in (key, *stems):
        fuzzy = _fuzzy_key(candidate)
        if fuzzy and fuzzy not in NEEDS_ENDING and fuzzy[0] == candidate[0]:  # typos rarely hit the first letter
            return frozenset(LATIN_GAZETTEER[fuzzy]), "fuzzy"
    return None


def _province_word(words: list[str], index: int) -> str | None:
    """Province named by words[index] ("kyonggido", "chonnam", or "kyongsang buk do"), else None."""
    word = words[index]
    for candidate in (word, *(word[: -len(e)] for e in ENDINGS if word.endswith(e) and len(word) - len(e) >= 5)):
        if (key := phonetic_key(candidate)) in LATIN_PROVINCE_KEYS:
            return LATIN_PROVINCE_KEYS[key]
    prefix = REGION_PREFIXES.get(phonetic_key(word))
    if prefix and index + 1 < len(words):
        return prefix.get(phonetic_key(words[index + 1])[:3])
    return None


def text_location(text: str) -> tuple[str, str, str] | None:
    """Return (province, city, match_type) for the first Korean place named in Latin/Cyrillic letters.

    match_type is 'exact', 'ending', 'fuzzy', or 'province' (only a province name was found).
    """
    words = TOKEN_PATTERN.findall(cyrillic_to_latin(post_body(text)).lower().replace("'", ""))
    provinces = [_province_word(words, index) for index in range(len(words))]
    mentioned = {province for province in provinces if province}
    for word, province in zip(words, provinces):
        if province or word in REGION_WORDS or len(word) < 4 or not (match := match_place_word(word)):
            continue
        places, match_type = match
        if len(places) > 1:  # e.g. Gwangju or Goseong: keep only places in a province the post names
            places = {place for place in places if place[0] in mentioned}
        if len(places) == 1:
            province, city = next(iter(places))
            return province, city, match_type
    if mentioned:
        return next(province for province in provinces if province), "", "province"
    return None


def discover_variants(
    texts, seeds: list[str], neighbours: int = 30, epochs: int = 5
) -> pd.DataFrame:
    """Train fastText on the posts and list the nearest words to each seed name, for manual review.

    `recognized_as` shows what `match_place_word` already makes of each variant; rows with an empty
    value are spellings to consider adding to LATIN_ALIASES (or false friends to add to NEEDS_ENDING).
    """
    import fasttext  # optional dependency, only needed for this exploration step

    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as corpus:
        for text in texts:
            words = TOKEN_PATTERN.findall(cyrillic_to_latin(post_body(str(text))).lower().replace("'", ""))
            if words:
                corpus.write(" ".join(words) + "\n")
    model = fasttext.train_unsupervised(
        corpus.name, model="skipgram", minn=2, maxn=5, dim=100, epoch=epochs, minCount=3, verbose=0
    )
    Path(corpus.name).unlink()
    rows = []
    for seed in seeds:
        for similarity, word in model.get_nearest_neighbors(seed.lower(), k=neighbours):
            match = match_place_word(word)
            rows.append({
                "seed": seed,
                "variant": word,
                "similarity": round(similarity, 3),
                "recognized_as": "; ".join(sorted(city for _, city in match[0])) if match else "",
                "match_type": match[1] if match else "",
            })
    return pd.DataFrame(rows)


def group_id_from_source(source_file: str) -> int | None:
    """Map a raw file name like group_1146665528.jsonl to its -100 channel ID."""
    match = re.fullmatch(r"group_(-?\d+)\.jsonl", source_file)
    if not match:
        return None
    raw_id = int(match.group(1))
    return raw_id if raw_id < 0 else int(f"-100{raw_id}")


def load_group_locations(groups_csv: Path) -> dict[int, tuple[str, str]]:
    with groups_csv.open(encoding="utf-8") as source:
        return {int(row["group_id"]): (row["province"], row["city"]) for row in csv.DictReader(source)}


def resolve_location(
    text: str, source_file: str, group_locations: dict[int, tuple[str, str]]
) -> tuple[str, str, str]:
    """Return (province, city, source), trying in order:

    'address' (Korean address in the post), 'text' (place name in Latin/Cyrillic letters),
    'group' (the group's province/city from telegram_groups.csv), else 'unknown'.
    """
    if found := address_location(text):
        return (*found, "address")
    if found := text_location(text):
        return found[0], found[1], "text"
    group_id = group_id_from_source(source_file)
    if group_id in group_locations:
        return (*group_locations[group_id], "group")
    return "", "", "unknown"
