"""
Konbit — Verifye tradiksyon frontend yo
Chemen: frontend/i18n/check_i18n.py

Kouri l depi konbit\\:
    python frontend\\i18n\\check_i18n.py

Li chèche chak tèks kreyòl kòd la itilize:
  - t('...') ak t("...") nan .js ak .html
  - eleman ki gen data-i18n, ak atribi ki nan data-i18n-attr
  - tèks nan fmt (wòl, kalite konje...) ak meni shell.js
epi li di, pou chak fichye <lang>.json, ki fraz ki MANKE ak ki fraz ki pa
sèvi ankò. Kòd sòti: 0 si tout lang yo konplè, 1 si pa.

    python frontend\\i18n\\check_i18n.py --json es   → fraz ki manke an es,
                                                     an JSON pare pou ranpli
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parent

# Tèks ki pase nan t() pa yon varyab, kidonk ki pa parèt kòm t('...'):
# kesyon ak opsyon pa defo yo (careers.html), fenèt detay paj akèy la,
# ak kèk mo komen. Ajoute kle a isit si w itilize l konsa.
DYNAMIC_KEYS_FILE = HERE / "dynamic_keys.json"

T_CALL = re.compile(r"""(?<![\w.])t\(\s*(?P<q>['"])(?P<key>(?:\\.|(?!(?P=q)).)*?)(?P=q)""")
# Meni shell.js: label: 'Tèks' / group: 'Tèks'
MAP_VALUE = re.compile(r"""(?:label|group):\s*'((?:\\.|[^'])*)'""")
# Estati ak badge: { draft: ['Bouyon', 'badge-pending'] }
BADGE_MAP = re.compile(r"""\[\s*'((?:\\.|[^'])*)'\s*,\s*'badge-""")
# Etikèt: label('Jou:', ...) — label() rele t() sou premye agiman an.
LABEL_CALL = re.compile(r"""(?<![\w.])label\(\s*'((?:\\.|[^'])*)'""")


def js_unescape(s: str) -> str:
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8") if "\\" in s else s


class I18nParser(HTMLParser):
    """Ranmase data-i18n (fèy sèlman) ak data-i18n-attr."""
    VOID = {"meta", "link", "input", "br", "img", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.keys = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for attr in (a.get("data-i18n-attr") or "").split():
            if a.get(attr):
                self.keys.add(a[attr])
        if tag in self.VOID:
            return
        if self.stack:
            self.stack[-1]["kids"] += 1
        self.stack.append({"i18n": "data-i18n" in a, "explicit": a.get("data-i18n") or "", "text": "", "kids": 0})

    def handle_endtag(self, tag):
        if tag in self.VOID or not self.stack:
            return
        el = self.stack.pop()
        if el["i18n"] and not el["kids"]:
            self.keys.add(el["explicit"] or el["text"].strip())
        if self.stack:
            self.stack[-1]["text"] += el["text"]

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"] += data


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in sorted(FRONTEND.glob("*.js")) + sorted(FRONTEND.glob("*.html")):
        text = path.read_text(encoding="utf-8-sig")
        for m in T_CALL.finditer(text):
            keys.add(js_unescape(m.group("key")))
        keys |= {js_unescape(v) for v in BADGE_MAP.findall(text)}
        keys |= {js_unescape(v) for v in LABEL_CALL.findall(text)}
        if path.suffix == ".html":
            parser = I18nParser()
            parser.feed(text)
            keys |= parser.keys
    # fmt.* ak NAV: valè kreyòl yo pase nan t() pa yon varyab.
    shell = (FRONTEND / "shell.js").read_text(encoding="utf-8-sig")
    keys |= {js_unescape(v) for v in MAP_VALUE.findall(shell)}
    for name in ("api.js", "shell.js"):
        text = (FRONTEND / name).read_text(encoding="utf-8-sig")
        for block in re.findall(r"=\s*\{\s*\n((?:\s*\w+:\s*'[^']*',?\s*\n)+)\s*\}\[", text):
            keys |= {js_unescape(v) for v in re.findall(r":\s*'((?:\\.|[^'])*)'", block)}
    if DYNAMIC_KEYS_FILE.exists():
        keys |= set(json.loads(DYNAMIC_KEYS_FILE.read_text(encoding="utf-8")))
    keys.discard("")
    return keys


def main() -> int:
    keys = used_keys()

    if len(sys.argv) == 3 and sys.argv[1] == "--json":
        lang = sys.argv[2]
        path = HERE / f"{lang}.json"
        have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        print(json.dumps({k: "" for k in sorted(keys) if not have.get(k)}, ensure_ascii=False, indent=1))
        return 0

    ok = True
    print(f"{len(keys)} fraz itilize nan frontend lan.\n")
    for path in sorted(HERE.glob("*.json")):
        if path.name == DYNAMIC_KEYS_FILE.name:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if not data.get(k))
        unused = sorted(k for k in data if k not in keys)
        status = "konplè" if not missing else f"{len(missing)} manke"
        print(f"{path.stem:>4}: {len(data) - len(unused)}/{len(keys)} — {status}"
              + (f", {len(unused)} pa sèvi ankò" if unused else ""))
        for k in missing[:15]:
            print(f"        manke: {k}")
        if len(missing) > 15:
            print(f"        … ak {len(missing) - 15} lòt")
        ok = ok and not missing
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())