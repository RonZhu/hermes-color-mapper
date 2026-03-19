#!/usr/bin/env python3
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = "https://ginzacelia.com"
LIMIT = 250
SLEEP_SEC = 0.2
ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "data" / "color_aliases.json"
OUT_PATH = ROOT / "docs" / "data" / "colors.json"

MATERIAL_HINTS = {
    "トゴ", "エプソン", "トリヨン", "トリヨンクレマンス", "スイフト", "シェーブル", "ボックスカーフ",
    "ヴォー", "ヴォースイフト", "トワル", "アニョー", "アニョーミロ", "ヴァッシュ", "ネゴンダ",
    "リザード", "クロコ", "アリゲーター", "オーストリッチ", "キャンバス", "デニム", "シルク",
}

HARDWARE_HINTS = [
    "ゴールド金具", "シルバー金具", "ピンクゴールド金具", "マットシャンパンゴールド金具",
    "シャンパンゴールド金具", "ブラック金具", "パラジウム金具", "ルテニウム金具",
]

BAG_MODELS = [
    "ミニケリー ドゥ", "ケリースポーツ", "コンスタンス エラン", "ガーデンパーティ ネオ", "エールバッグ ジップ ミニ",
    "ガーデンパーティ", "ピコタンロック", "ピコタン", "エブリン", "リンディ", "ボリード", "ケリー", "バーキン", "コンスタンス",
]


def fetch_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JarvisColorMapper/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def split_tokens(title: str):
    # shopify titles here are commonly separated by multiple spaces
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


def detect_hardware(tokens):
    found = []
    for t in tokens:
        for h in HARDWARE_HINTS:
            if h in t:
                found.append(h)
    # preserve order, unique
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
        if any(h in s for h in MATERIAL_HINTS):
            continue
        if re.search(r"\d", s):
            # often size like 25, 28 etc
            if len(s) <= 4:
                continue
        # likely color candidate
        return s
    return ""


def normalize_key(s: str):
    return re.sub(r"\s+", "", s).lower()


def main():
    aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8")) if ALIASES_PATH.exists() else {}

    all_products = []
    page = 1
    while True:
        url = f"{BASE}/products.json?limit={LIMIT}&page={page}"
        data = fetch_json(url)
        products = data.get("products", [])
        if not products:
            break
        all_products.extend(products)
        if len(products) < LIMIT:
            break
        page += 1
        time.sleep(SLEEP_SEC)

    by_color = defaultdict(lambda: {
        "ja": "",
        "en": "",
        "fr": "",
        "zh": "",
        "aliases": [],
        "examples": [],
        "source": "ginzacelia",
    })

    for p in all_products:
        title = p.get("title", "")
        if not title:
            continue
        tokens = split_tokens(title)
        model = detect_model(tokens)
        if not model:
            continue
        hardware = detect_hardware(tokens)
        color_ja = infer_color(tokens, model, hardware)
        if not color_ja:
            continue

        key = normalize_key(color_ja)
        entry = by_color[key]

        entry["ja"] = entry["ja"] or color_ja

        manual = aliases.get(color_ja) or aliases.get(key) or {}
        for k in ["en", "fr", "zh", "ja"]:
            if manual.get(k):
                entry[k] = manual[k]
        if manual.get("aliases"):
            entry["aliases"] = list(dict.fromkeys(entry["aliases"] + manual["aliases"]))

        example = {
            "bag": model or "",
            "hardware": hardware[0] if hardware else "",
            "title": title,
            "url": f"{BASE}/products/{p.get('handle','')}",
        }
        if len(entry["examples"]) < 12:
            entry["examples"].append(example)

    colors = []
    for _, v in by_color.items():
        # fallback names
        v["en"] = v["en"] or ""
        v["fr"] = v["fr"] or ""
        v["zh"] = v["zh"] or ""
        # auto aliases
        if v["ja"]:
            v["aliases"] = list(dict.fromkeys(v["aliases"] + [v["ja"]]))
        colors.append(v)

    colors.sort(key=lambda x: (x["ja"] or "", x["en"] or ""))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generatedAt": int(time.time()),
        "source": BASE,
        "count": len(colors),
        "items": colors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Fetched products: {len(all_products)}")
    print(f"Extracted colors: {len(colors)}")
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
