import requests
from bs4 import BeautifulSoup
import re

url = "https://support.microsoft.com/en-us/windows/apps/use-the-calculator-in-windows"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "html.parser")
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if "paint" in href.lower() or "paint" in text.lower() or "app" in href.lower():
        print(text, "->", href)
