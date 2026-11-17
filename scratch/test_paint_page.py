import requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}
r = requests.get("https://www.microsoft.com/en-us/windows/paint", headers=headers)
print("Status:", r.status_code, "URL:", r.url, "Len:", len(r.text))
from core_organs.professor.knowledge import manual_rag as MR
txt = MR._html_to_text(r.text)
print("Text sample:\n", txt[:1200])
