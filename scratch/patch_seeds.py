import ast
import io
import json

# ---------------------------------------------------------------- guide_finder: seeds may be {"url","depth","pages"}
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''    for url in seeds:
        status, _ct, body, _f = fetch(url)
        if status == 200 and body:
            out.append({"url": url, "title": "seed", "score": 8.0, "why": ["official documentation root (seed list, verified to answer)"], "kind": "seed"})''', '''    for sd in seeds:
        url = sd["url"] if isinstance(sd, dict) else sd
        status, _ct, body, _f = fetch(url)
        if status == 200 and body:
            ent = {"url": url, "title": "seed", "score": 8.0, "why": ["official documentation root (seed list, verified to answer)"], "kind": "seed"}
            if isinstance(sd, dict):
                ent.update({k: sd[k] for k in ("depth", "pages") if k in sd})
            out.append(ent)''')
rep('''                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline, keep=topic)''',
    '''                    pages, sk = crawl(c["url"], fetch, robots, max_pages=int(c.get("pages", max_pages)), max_depth=int(c.get("depth", max_depth)), delay_s=delay_s, allow_local=allow_local_net,
                                      deadline=deadline, keep=topic)''')
rep('''                    if time.time() > deadline or got >= sources_wanted:
                        break''', '''                    if time.time() > deadline or (got >= sources_wanted and c.get("kind") != "seed"):
                        break''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

# ---------------------------------------------------------------- catalog: official URLs located with a web search (2026-10-10); each is fetched at run time and used only if it answers
C = "D:/new_automation/All codes/core_organs/professor/data/app_catalog.json"
cat = json.load(io.open(C, "r", encoding="utf-8"))
SEEDS = {
    "notepad": [{"url": "https://support.microsoft.com/en-us/windows/apps/help-in-notepad", "depth": 0, "pages": 1},
                {"url": "https://support.microsoft.com/en-us/windows/enhance-your-writing-with-ai-in-notepad-4088b954-c97b-46dc-813f-959be01746d5", "depth": 0, "pages": 1},
                {"url": "https://learn.microsoft.com/en-us/windows/client-management/manage-notepad", "depth": 0, "pages": 1}],
    "mspaint": [{"url": "https://support.microsoft.com/en-us/windows/open-microsoft-paint-ead1dc5c-abc4-fd2c-d81e-ebb013fbc113", "depth": 0, "pages": 1},
                {"url": "https://support.microsoft.com/en-gb/windows/help-in-paint-d62e155a-1775-6da4-0862-62a3e9e5a511", "depth": 0, "pages": 1},
                {"url": "https://support.microsoft.com/en-us/windows/ai/ai-apps/use-copilot-pc-features-in-paint", "depth": 0, "pages": 1}],
    "winword": [{"url": "https://support.microsoft.com/en-us/word/", "depth": 1, "pages": 60}, {"url": "https://support.microsoft.com/en-us/word/training/learn-more-about-word", "depth": 1, "pages": 30},
                {"url": "https://support.microsoft.com/en-us/word/training/create-a-document-in-word", "depth": 0, "pages": 1},
                {"url": "https://support.microsoft.com/en-us/office/word-for-new-users-cace0fd8-eed9-4aa2-b3c6-07d39895886c", "depth": 0, "pages": 1}],
    "powerpnt": [{"url": "https://support.microsoft.com/en-us/office/powerpoint-help-5395bb85-eb6f-47fa-b5af-52996bac819e", "depth": 1, "pages": 40},
                 {"url": "https://support.microsoft.com/en-us/powerpoint/training/learn-more-about-powerpoint", "depth": 1, "pages": 30},
                 {"url": "https://support.microsoft.com/en-us/office/basic-tasks-for-creating-a-powerpoint-presentation-efbbc1cd-c5f1-4264-b48e-c8a7b0334e36", "depth": 0, "pages": 1},
                 {"url": "https://support.microsoft.com/en-us/accessibility/powerpoint/use-keyboard-shortcuts-to-create-powerpoint-presentations", "depth": 0, "pages": 1}],
    "systemsettings": [{"url": "https://support.microsoft.com/en-us/accessibility/windows/understand-and-explore-windows-settings", "depth": 0, "pages": 1},
                       {"url": "https://support.microsoft.com/en-us/accessibility/windows/use-a-screen-reader-to-explore-and-navigate-settings-in-windows", "depth": 0, "pages": 1},
                       {"url": "https://support.microsoft.com/en-us/windows/power-settings-in-windows-11-0d6a2b6b-2e87-4611-9980-ac9ea2175734", "depth": 0, "pages": 1},
                       {"url": "https://support.microsoft.com/en-us/windows/change-default-apps-in-windows", "depth": 0, "pages": 1}],
    "whatsapp": [{"url": "https://faq.whatsapp.com/", "depth": 1, "pages": 50}],
}
for a in cat["apps"]:
    if a["key"] in SEEDS:
        a["seeds"] = SEEDS[a["key"]]
cat["_provenance"] = "tier 1-2 seeds: official pages located with a web search on 2026-10-10 (not written by the Professor); each is fetched at run time and ignored unless it answers HTTP 200"
io.open(C, "w", encoding="utf-8", newline="\n").write(json.dumps(cat, indent=2, ensure_ascii=False))
print("seeds updated;", sum(1 for a in cat["apps"] if a.get("seeds")), "apps with seeds")
