#!/usr/bin/env python3
import json
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

CELIA_BASE = "https://ginzacelia.com"
XIAOMA_BASE = "https://ginzaxiaoma.com"
LIMIT = 250
SLEEP_SEC = 0.2
ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "data" / "color_aliases.json"
OUT_PATH = ROOT / "docs" / "data" / "colors.json"

MATERIAL_HINTS_JA = {
    "トゴ", "エプソン", "トリヨン", "トリヨンクレマンス", "スイフト", "シェーブル", "ボックスカーフ",
    "ヴォー", "ヴォースイフト", "トワル", "アニョー", "アニョーミロ", "ヴァッシュ", "ネゴンダ",
    "リザード", "クロコ", "アリゲーター", "オーストリッチ", "キャンバス", "デニム", "シルク",
}
MATERIAL_HINTS_EN = {
    "Swift", "Epsom", "Togo", "Clemence", "Chevre", "Evercolor", "Box-calf", "Sombrero",
    "Barenia", "Vache", "Toile", "Alligator", "Crocodile", "Ostrich", "Canvas", "Denim",
}

HARDWARE_HINTS_JA = [
    "マットシャンパンゴールド金具", "シャンパンゴールド金具", "ピンクゴールド金具",
    "ゴールド金具", "シルバー金具", "ブラック金具", "パラジウム金具", "ルテニウム金具",
]
HARDWARE_HINTS_EN = [
    "Rose Gold hardware", "Palladium hardware", "Permabrass hardware", "Gold hardware", "Silver hardware", "Enamel hardware",
]

BAG_MODELS = [
    "ミニケリー ドゥ", "ケリースポーツ", "コンスタンス エラン", "ガーデンパーティ ネオ", "エールバッグ ジップ ミニ",
    "ガーデンパーティ", "ピコタンロック", "ピコタン", "エブリン", "リンディ", "ボリード", "ケリー", "バーキン", "コンスタンス",
    "Mini Kelly", "Kelly Pochette", "Kelly", "Birkin", "Constance", "Picotin Lock", "Picotin", "Lindy", "Bolide", "Herbag", "Garden Party", "Roulis", "Evelyne",
]


def fetch_text(url: str, accept: str = "text/html,*/*"):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JarvisColorMapper/1.1)",
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8,zh-CN;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_json(url: str):
    return json.loads(fetch_text(url, accept="application/json,text/plain,*/*"))


def split_tokens(title: str):
    rough = [x.strip() for x in re.split(r"\s{2,}|\s\|\s", title) if x.strip()]
    if len(rough) <= 1:
        t = re.sub(r"\s+", " ", title).strip()
        rough = [x.strip() for x in t.split(" ") if x.strip()]
    return rough


def detect_model(tokens):
    joined = " ".join(tokens)
    for m in BAG_MODELS:
        if m in joined:
            return m
    return ""


def detect_hardware(tokens, title=""):
    found = []
    joined = " ".join(tokens)
    haystacks = [title, joined] + tokens

    for hs in haystacks:
        if not hs:
            continue
        for h in HARDWARE_HINTS_JA + HARDWARE_HINTS_EN:
            if h in hs:
                found.append(h)

        # Generic JP capture: something金具 (e.g. エレクトラム金具)
        for m in re.finditer(r"([ァ-ヶ一-龯A-Za-z・ー\-]{1,16}金具)", hs):
            found.append(m.group(1).strip())

        # Generic EN capture: XXX hardware
        for m in re.finditer(r"((?:Rose\s+Gold|Gold|Silver|Palladium|Permabrass|Enamel|Electrum)\s+hardware)", hs, re.I):
            v = " ".join(m.group(1).split())
            # normalize casing for consistency
            parts = v.split(" ")
            if len(parts) >= 2:
                v = " ".join([parts[0].title(), parts[1].lower()])
            found.append(v)

    return list(dict.fromkeys(found))


def is_stamp_or_noise(token: str):
    return (
        "刻印" in token
        or "HERMES" in token
        or "エルメス" in token
        or token in {"SPO", "PM", "MM", "GM", "TPM", "新品", "未使用", "新品同様"}
        or bool(re.fullmatch(r"[A-Z]\b", token))
    )


def infer_color(tokens, model, hardware):
    for t in tokens:
        s = t.strip()
        if not s:
            continue
        if model and model in s:
            continue
        if any((b in s) or (s in b) for b in BAG_MODELS):
            continue
        if any(h in s for h in hardware):
            continue
        if is_stamp_or_noise(s):
            continue
        if any(h in s for h in MATERIAL_HINTS_JA) or any(h in s for h in MATERIAL_HINTS_EN):
            continue
        if re.search(r"\d", s) and len(s) <= 4:
            continue
        return s
    return ""


def normalize_key(s: str):
    return re.sub(r"\s+", "", s).lower()


def find_manual_alias(aliases: dict, color: str, key: str):
    if color in aliases:
        return aliases[color]
    if key in aliases:
        return aliases[key]
    for _, v in aliases.items():
        for a in v.get("aliases", []):
            if normalize_key(a) == key:
                return v
    return {}


def infer_color_from_official_aliases(title: str, aliases: dict) -> str:
    tkey = normalize_key(title)
    best = (0, "")
    for _, v in aliases.items():
        if v.get("official") is not True:
            continue
        ja = v.get("ja", "")
        for a in ([ja] + v.get("aliases", [])):
            ak = normalize_key(a)
            if len(ak) < 3:
                continue
            if ak in tkey and len(ak) > best[0]:
                best = (len(ak), ja)
    return best[1]


def extract_celia_products():
    rows = []
    # Celia has reliable JA + EN product feeds
    for locale, prefix in [("ja", ""), ("en", "/en")]:
        page = 1
        while True:
            data = fetch_json(f"{CELIA_BASE}{prefix}/products.json?limit={LIMIT}&page={page}")
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                title = p.get("title", "")
                if not title:
                    continue
                rows.append({
                    "title": title,
                    "url": f"{CELIA_BASE}/products/{p.get('handle','')}",
                    "source": "celia",
                    "lang": locale,
                })
            if len(products) < LIMIT:
                break
            page += 1
            time.sleep(SLEEP_SEC)
    return rows


def extract_xiaoma_products_from_newin():
    # XIAOMA newin pages are localized: /newin (en), /ja/newin, /zh-CN/newin
    rows = []
    card_re = re.compile(
        r'<a href="((?:/(?:ja|zh-CN))?/product/[0-9]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<p[^>]*>(.*?)</p>',
        re.S,
    )
    locales = [("en", "/newin"), ("ja", "/ja/newin"), ("zh", "/zh-CN/newin")]
    for locale, path in locales:
        html = fetch_text(f"{XIAOMA_BASE}{path}")
        for m in card_re.finditer(html):
            href, title, p1 = m.group(1), m.group(2), m.group(3)
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
            p1 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", p1)).strip()
            if not title:
                continue
            rows.append({
                "title": f"{title} {p1}".strip(),
                "url": f"{XIAOMA_BASE}{href}",
                "source": "xiaoma",
                "lang": locale,
            })
    return rows


def canonical_bag(bag: str) -> str:
    b = (bag or "").lower()
    if "ケリー" in bag or "kelly" in b:
        return "kelly"
    return re.sub(r"\s+", "", b)


def canonical_hardware(hw: str) -> str:
    h = (hw or "").lower()
    if "ゴールド金具" in hw or "gold hardware" in h:
        return "gold"
    if "シルバー金具" in hw or "silver hardware" in h:
        return "silver"
    if "パラジウム" in hw or "palladium" in h:
        return "palladium"
    return re.sub(r"\s+", "", h)


def upsert_entry(by_color, key, color_ja, aliases, model, hardware, title, url, source, lang=""):
    entry = by_color[key]
    entry["ja"] = entry["ja"] or color_ja

    manual = find_manual_alias(aliases, color_ja, key)
    # Strict mode: never auto-fill multilingual names unless explicitly marked official.
    if manual.get("official") is True:
        for k in ["en", "fr", "zh", "ja"]:
            if manual.get(k):
                entry[k] = manual[k]
    if manual.get("aliases"):
        entry["aliases"] = list(dict.fromkeys(entry["aliases"] + manual["aliases"]))

    bag = model or ""
    hw = hardware[0] if hardware else ""

    # Merge cross-source duplicate hits by product signature.
    # User rule: same hit when bag+hardware match (e.g. ケリー + ゴールド金具).
    cbag = canonical_bag(bag)
    chw = canonical_hardware(hw)
    for ex in entry["examples"]:
        if canonical_bag(ex.get("bag", "")) == cbag and canonical_hardware(ex.get("hardware", "")) == chw and cbag and chw:
            srcs = set(str(ex.get("source", "")).split("+"))
            srcs.add(source)
            ex["source"] = "+".join(sorted(s for s in srcs if s))
            return

    example = {
        "bag": bag,
        "hardware": hw,
        "title": title,
        "url": url,
        "source": source,
        "lang": lang,
    }
    if len(entry["examples"]) < 18:
        entry["examples"].append(example)


def main():
    aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8")) if ALIASES_PATH.exists() else {}

    by_color = defaultdict(lambda: {
        "ja": "", "en": "", "fr": "", "zh": "", "aliases": [], "examples": []
    })

    celia_rows = extract_celia_products()
    xiaoma_rows = extract_xiaoma_products_from_newin()

    for row in celia_rows + xiaoma_rows:
        tokens = split_tokens(row["title"])
        model = detect_model(tokens)
        if not model:
            continue
        hardware = detect_hardware(tokens, row["title"])
        color_ja = ""
        if row["source"] == "xiaoma":
            color_ja = infer_color_from_official_aliases(row["title"], aliases)
        if not color_ja:
            color_ja = infer_color(tokens, model, hardware)
        if not color_ja:
            continue
        key = normalize_key(color_ja)

        manual = find_manual_alias(aliases, color_ja, key)
        if manual.get("official") is True and manual.get("ja"):
            color_ja = manual["ja"]
            key = normalize_key(color_ja)

        upsert_entry(by_color, key, color_ja, aliases, model, hardware, row["title"], row["url"], row["source"], row.get("lang", ""))

    # ensure manual alias dictionary can create standalone entries (even if not seen in products yet)
    for k, manual in aliases.items():
        key = normalize_key(manual.get("ja") or k)
        if key not in by_color:
            by_color[key] = {
                "ja": manual.get("ja") or k,
                "en": manual.get("en", "") if manual.get("official") is True else "",
                "fr": manual.get("fr", "") if manual.get("official") is True else "",
                "zh": manual.get("zh", "") if manual.get("official") is True else "",
                "aliases": manual.get("aliases", []),
                "examples": [],
            }

    colors = []
    for v in by_color.values():
        v["en"] = v["en"] or ""
        v["fr"] = v["fr"] or ""
        v["zh"] = v["zh"] or ""
        if v["ja"]:
            v["aliases"] = list(dict.fromkeys(v["aliases"] + [v["ja"]]))
        colors.append(v)

    colors.sort(key=lambda x: (x["ja"] or "", x["en"] or ""))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generatedAt": int(time.time()),
        "source": [CELIA_BASE, XIAOMA_BASE],
        "counts": {"celia_products": len(celia_rows), "xiaoma_products": len(xiaoma_rows)},
        "count": len(colors),
        "items": colors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Fetched CELIA products: {len(celia_rows)}")
    print(f"Fetched XIAOMA products: {len(xiaoma_rows)}")
    print(f"Extracted colors: {len(colors)}")
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
