import json
import os
import re
import time
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGET_URL = "https://salihli.adalet.gov.tr/"
SEEN_FILE = "seen.json"
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

CHECK_INTERVAL_SECONDS = 60
CHECKS_PER_RUN = 1

PRIORITY_KEYWORDS = (
    "zabıt", "zabit", "katip", "kâtip", "nihai",
    "sonuç", "sonuc", "mülakat", "mulakat", "sözlü", "sozlu", "personel"
)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False},
        timeout=20,
    )
    resp.raise_for_status()


def fetch_announcements() -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(TARGET_URL, headers=headers, timeout=25)
    except requests.exceptions.SSLError:
        resp = requests.get(TARGET_URL, headers=headers, timeout=25, verify=False)

    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    items: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        full_url = urljoin(TARGET_URL, href)
        if "salihli.adalet.gov.tr" not in full_url.lower():
            continue

        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if len(title) < 15:
            continue

        items[full_url] = title

    return items


def save_seen(data: dict[str, str]) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    first_run = not os.path.exists(SEEN_FILE)

    if first_run:
        try:
            current = fetch_announcements()
        except Exception as exc:
            send_telegram(
                f"⚠️ Salihli Adliyesi sitesine ilk bağlantıda erişilemedi.\nHata: {exc}"
            )
            raise

        save_seen(current)
        if not current:
            send_telegram(
                "⚠️ Siteye bağlanıldı ancak duyuru linki okunamadı."
            )
            return

        sample = "\n".join(f"• {t}" for t in list(current.values())[:5])
        send_telegram(
            f"✅ Salihli Adliyesi hızlı takip botu aktif!\n\n"
            f"Toplam {len(current)} bağlantı kaydedildi. Örnek kayıtlar:\n{sample}\n\n"
            f"Site yaklaşık her 1 dakikada bir kontrol edilecek."
        )
        return

    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen: dict[str, str] = json.load(f)

    for attempt in range(CHECKS_PER_RUN):
        try:
            current = fetch_announcements()
        except Exception as exc:
            print(f"[{attempt + 1}/{CHECKS_PER_RUN}] Bağlantı hatası: {exc}")
        else:
            new_items = [
                (url, title)
                for url, title in current.items()
                if url not in seen or seen[url] != title
            ]

            if new_items:
                for url, title in new_items:
                    is_priority = any(
                        kw in title.lower() for kw in PRIORITY_KEYWORDS
                    )
                    header = (
                        "🚨 ÖNEMLİ DUYURU - Salihli Adliyesi"
                        if is_priority
                        else "📢 Yeni Duyuru - Salihli Adliyesi"
                    )
                    send_telegram(f"{header}\n\n{title}\n\n🔗 {url}")

                seen.update(current)
                save_seen(seen)
                print(f"{len(new_items)} yeni duyuru bildirildi.")
                return

            print(f"[{attempt + 1}/{CHECKS_PER_RUN}] Yeni duyuru yok.")

        if attempt < CHECKS_PER_RUN - 1:
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
