import re
import requests
from bs4 import BeautifulSoup

URL = "https://1000mostcommonwords.com/1000-most-common-uzbek-words/"
OUT = "words.txt"

def norm_word(w: str) -> str:
    w = w.strip().lower()
    # apostrof variantlarini bir xil qilamiz
    w = w.replace("’", "'").replace("ʻ", "'").replace("ʼ", "'").replace("`", "'")
    w = re.sub(r"\s+", " ", w).strip()
    return w

def main():
    r = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    table = soup.find("table")
    if not table:
        raise RuntimeError("Table topilmadi. Sayt strukturasi o'zgargan bo'lishi mumkin.")

    # Headerlardan "Uzbek" ustun indexini topamiz
    header = table.find("tr")
    ths = [th.get_text(strip=True).lower() for th in header.find_all(["th", "td"])]
    if "uzbek" not in ths:
        raise RuntimeError(f"Headerda 'Uzbek' topilmadi. Headerlar: {ths}")

    uz_idx = ths.index("uzbek")

    words = []
    seen = set()

    rows = table.find_all("tr")[1:]  # headerdan keyin
    for row in rows:
        cols = row.find_all(["td", "th"])
        if len(cols) <= uz_idx:
            continue

        w = cols[uz_idx].get_text(" ", strip=True)
        w = norm_word(w)

        if not w:
            continue

        # faqat bitta so'z (frazalarni tashlaymiz)
        if " " in w:
            continue

        # faqat lotin harflari + apostrof/defis (siz xohlasangiz kengaytiramiz)
        if not re.fullmatch(r"[a-z'\-]+", w):
            continue

        if w not in seen:
            seen.add(w)
            words.append(w)

    if not words:
        raise RuntimeError("So'zlar chiqmadi. Ehtimol sayt kontenti JS bilan kelayotgandir.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(words))

    print(f"✅ {len(words)} ta so'z yozildi -> {OUT}")

if __name__ == "__main__":
    main()
