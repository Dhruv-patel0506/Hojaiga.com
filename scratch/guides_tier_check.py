import json
r = json.load(open(r'd:\new_automation\data\professor\guides\corpus_report.json', encoding='utf-8'))
apps = {a['key']: a for a in r['apps']}
for k in ('winword', 'powerpnt', 'excel', 'mspaint', 'notepad', 'systemsettings', 'discord', 'whatsapp', 'telegram', 'obs64', 'blender', 'chrome', 'code', 'calculator'):
    a = apps.get(k) or {}
    print(f"{k:16s} docs={a.get('documents', 0):3d} chunks={a.get('chunks', 0):5d} kinds={a.get('kinds')} err={str(a.get('error'))[:60]}")
