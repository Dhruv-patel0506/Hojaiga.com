import json, glob, os, sys

def json3_to_lines(path):
    d = json.load(open(path, encoding='utf-8'))
    out = []
    for ev in d.get('events', []):
        segs = ev.get('segs')
        if not segs:
            continue
        txt = ''.join(s.get('utf8', '') for s in segs).replace('\n', ' ').strip()
        if not txt:
            continue
        t = ev.get('tStartMs', 0) / 1000.0
        out.append((t, txt))
    # dedupe consecutive repeats
    ded = []
    for t, x in out:
        if ded and ded[-1][1].lower() == x.lower():
            continue
        ded.append((t, x))
    return ded

for vid in ['1fcfZ_Ne8ok', 'hDKCxebp88A']:
    p = f'{vid}.en.json3'
    if not os.path.exists(p):
        p = sorted(glob.glob(f'{vid}*.json3'))[0]
    lines = json3_to_lines(p)
    info = json.load(open(f'{vid}.info.json', encoding='utf-8'))
    with open(f'{vid}_transcript.txt', 'w', encoding='utf-8') as f:
        f.write(f"TITLE: {info.get('title')}\nUPLOADER: {info.get('uploader')}\nDURATION: {info.get('duration')}\n")
        ch = info.get('chapters') or []
        if ch:
            f.write("CHAPTERS:\n")
            for c in ch:
                f.write(f"  [{int(c.get('start_time',0))//60:02d}:{int(c.get('start_time',0))%60:02d}] {c.get('title')}\n")
        f.write("DESCRIPTION:\n" + (info.get('description') or '')[:4000] + "\n\nTRANSCRIPT:\n")
        for t, x in lines:
            f.write(f"[{int(t)//60:02d}:{int(t)%60:02d}] {x}\n")
    print(vid, '|', info.get('title'), '|', round((info.get('duration') or 0)/60, 1), 'min |', len(lines), 'lines')
