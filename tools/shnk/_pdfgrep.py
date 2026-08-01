import sys, re, fitz
path, kws = sys.argv[1], sys.argv[2].split('|')
doc = fitz.open(path)
print(f'### {path} | страниц: {doc.page_count}')
for pno in range(doc.page_count):
    txt = doc[pno].get_text()
    low = txt.lower()
    for kw in kws:
        if kw.lower() in low:
            # печать строк с контекстом
            for ln in txt.splitlines():
                if kw.lower() in ln.lower() and ln.strip():
                    print(f'p{pno+1} [{kw}] {ln.strip()[:160]}')
            break
