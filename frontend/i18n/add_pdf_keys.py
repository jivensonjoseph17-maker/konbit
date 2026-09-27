"""
Konbit — Ajoute 2 fraz bouton PDF yo nan tout fichye lang yo
Chemen: frontend/i18n/add_pdf_keys.py

Kouri l YON FWA depi konbit\\:
    python frontend\\i18n\\add_pdf_keys.py
Apre sa ou ka efase l.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

KEYS = ["Telechaje PDF", "Ap prepare PDF la…"]
T = {
    "fr": ["Télécharger le PDF", "Préparation du PDF…"],
    "en": ["Download PDF", "Preparing the PDF…"],
    "es": ["Descargar PDF", "Preparando el PDF…"],
    "pt": ["Baixar PDF", "Preparando o PDF…"],
    "de": ["PDF herunterladen", "PDF wird erstellt…"],
    "zh": ["下载 PDF", "正在生成 PDF…"],
    "ar": ["تنزيل PDF", "جارٍ تجهيز ملف PDF…"],
}

for lang in ["ht", *T]:
    path = HERE / f"{lang}.json"
    if not path.exists():
        print(f"{lang:>3}: pa gen {path.name} — sote")
        continue
    values = KEYS if lang == "ht" else T[lang]
    data = json.loads(path.read_text(encoding="utf-8"))
    added = 0
    for key, value in zip(KEYS, values):
        if not data.get(key):
            data[key] = value
            added += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{lang:>3}: {added} fraz ajoute")