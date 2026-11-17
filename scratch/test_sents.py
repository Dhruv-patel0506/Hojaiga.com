from core_organs.professor.knowledge import manual_rag as MR, guide_explain as GEX
ix = MR.ManualIndex()
sents = GEX.sentences(ix, "calculator")
for fs, s, c in sents:
    if any(w in fs for w in ["standard", "scientific", "graphing", "programmer", "currency"]):
        print("FS:", fs)
        print("S: ", s)
