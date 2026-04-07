import os, re

FILES = [
    'backend/app/main.py',
    'backend/app/rag.py',
    'backend/app/ingest.py',
    'backend/app/llm_client.py',
    'backend/app/search.py',
    'backend/app/auth.py',
    'backend/app/dbmanage.py',
    'backend/app/web_search.py',
    'backend/app/history.py',
    'backend/app/feedback_manager.py',
]

FR_WORDS = {'pour','les','dans','avec','sur','une','des','est','par','qui','que',
    'pas','son','ses','tout','comme','mais','car','donc','aussi','peut','être',
    'depuis','lors','afin','ainsi','selon','vers','entre','chez','très','après',
    'avant','sous','sans','cette','ligne','fichier','nouveau','même','chaque',
    'autre','leur','retour','quand','encore','toute','tous','aucun','trouve',
    'donne','utilise','lors','celui','ceux','tels','sinon','plus','moins',
    "d'un","d'une","d'experts","n'est","s'attend","c'est","n'oublie","qu'il","qu'on"}

FR_PAT = re.compile(r"\b(" + "|".join(re.escape(w) for w in FR_WORDS) + r")\b", re.IGNORECASE)

# Corrupt patterns
CORRUPT_PAT = re.compile(
    r'Ã[©¨ÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖרÙÚÛÜÝÞß\xa0 ]'
    r'|â€[™œ""\x9c\x9d\x99]'
    r'|Â°|Â«|Â»'
    r'|â˜[â˜\']'
    r'|â€"|â€"'
)

def has_emoji(s):
    # Only checks basic emoji blocks to avoid matching normal punctuation
    for c in s:
        cp = ord(c)
        if (0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x1F900 <= cp <= 0x1F9FF):
            return repr(c)
    return None

def classify(text):
    text = text.strip()
    if not text or text.startswith('=') or text.startswith('-') or len(text) < 5:
        return 'skip'
    hits = len(FR_PAT.findall(text))
    return 'fr' if hits >= 2 else 'en'

totals = {'en': 0, 'fr': 0}
by_file = {}
fr_lines = []
corrupt_lines = []
emoji_lines = []

for fpath in FILES:
    if not os.path.exists(fpath):
        continue
    fname = os.path.basename(fpath)
    counts = {'en': 0, 'fr': 0}
    lines = open(fpath, encoding='utf-8', errors='replace').readlines()
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        # Check corrupt
        if 'Ã' in line or re.search(r'â€[^\w]|â˜|â–|Â[^a-zA-Z]', line):
            corrupt_lines.append((fname, i, line.strip()))
            
        # Check emojis
        em = has_emoji(line)
        if em:
            emoji_lines.append((fname, i, line.strip(), em))
            
        # Check Lang
        m = re.match(r'\s*#\s*(.*)', line)
        if m:
            lang = classify(m.group(1))
            if lang != 'skip':
                counts[lang] += 1
                totals[lang] += 1
                if lang == 'fr':
                    fr_lines.append((fname, i, line.strip()))
        m2 = re.match(r'\s*"""(.*?)"""', line)
        if m2:
            lang = classify(m2.group(1))
            if lang != 'skip':
                counts[lang] += 1
                totals[lang] += 1
                if lang == 'fr':
                    fr_lines.append((fname, i, line.strip()))
    by_file[fname] = counts

out = open('audit_global.txt', 'w', encoding='utf-8')
out.write("=== 1. RATIO EN / FR ===\n")
out.write(f"{'File':<25} {'EN':>5} {'FR':>5} {'%EN':>7}\n")
out.write("-" * 45 + "\n")
for fname, c in by_file.items():
    total = c['en'] + c['fr']
    pct = f"{100*c['en']//total}%" if total else "N/A"
    out.write(f"{fname:<25} {c['en']:>5} {c['fr']:>5} {pct:>7}\n")
out.write("-" * 45 + "\n")
total_all = totals['en'] + totals['fr']
pct_all = f"{100*totals['en']//total_all}%" if total_all else "N/A"
out.write(f"{'TOTAL':<25} {totals['en']:>5} {totals['fr']:>5} {pct_all:>7}\n\n")

if fr_lines:
    out.write("FR Lines Remaining:\n")
    for fname, lineno, text in fr_lines:
        out.write(f"  {fname}:L{lineno}: {text}\n")
else:
    out.write("✅ Zero French sentences detected.\n")

out.write("\n=== 2. EMOJIS ===\n")
if emoji_lines:
    for fname, lineno, text, em in emoji_lines:
        out.write(f"  {fname}:L{lineno} [{em}]: {text}\n")
else:
    out.write("✅ Zero Emojis detected.\n")

out.write("\n=== 3. TERMINAL ARTIFACTS / MOJIBAKE ===\n")
if corrupt_lines:
    for fname, lineno, text in corrupt_lines:
        out.write(f"  {fname}:L{lineno}: {text}\n")
else:
    out.write("✅ Zero Terminal artifacts detected.\n")

out.close()
print("Audit complete")
