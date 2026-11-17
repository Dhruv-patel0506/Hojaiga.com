import requests
from bs4 import BeautifulSoup
import re

url = "https://www.bing.com/search?q=site%3Asupport.microsoft.com%2Fen-us%2Fwindows+paint+tools+layers&setlang=en"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
from core_organs.professor.knowledge.guide_finder import parse_bing
results = parse_bing(r.text)
for res in results:
    print(res["title"], "->", res["url"])
