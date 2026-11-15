#!/usr/bin/env python3
"""Check translations: every source string must have a translation in revenant_i18n/<lang>.json.

Source strings (English) are collected from
  revenant.py               tr("...") and N_("...")   (parsed with ast, so implicit concatenation works)
  revenant_web/app.js       t("...")
  revenant_web/index.html   text of elements with data-i18n, values of data-i18n-placeholder / data-i18n-title

  python tools/i18n_check.py            report missing and unused translations (exit 1 if something is missing)
  python tools/i18n_check.py --add      also add missing strings to the catalogs (value = English, marked TODO)
"""
import ast, html.parser, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "revenant_i18n"


def from_python(path):
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            found.add(node.args[0].value)
    return found


def from_js(path):
    src = path.read_text(encoding="utf-8")
    return {json.loads(f'"{m}"') for m in re.findall(r'\bt\(\s*"((?:[^"\\]|\\.)*)"', src)}


class _HtmlStrings(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.found, self.stack = set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for attr in ("data-i18n-placeholder", "data-i18n-title"):
            if a.get(attr):
                self.found.add(a[attr])
        if tag in ("input", "br", "img", "meta", "link"):
            return
        self.stack.append([] if "data-i18n" in a else None)

    def handle_endtag(self, tag):
        if self.stack:
            parts = self.stack.pop()
            if parts is not None:
                self.found.add(" ".join("".join(parts).split()))

    def handle_data(self, data):
        for parts in self.stack:
            if parts is not None:
                parts.append(data)


def from_html(path):
    p = _HtmlStrings()
    p.feed(path.read_text(encoding="utf-8"))
    return p.found


def main():
    sources = (from_python(ROOT / "revenant.py") | from_js(ROOT / "revenant_web" / "app.js")
               | from_html(ROOT / "revenant_web" / "index.html"))
    failed = False
    for cat_path in sorted(I18N.glob("*.json")):
        cat = json.loads(cat_path.read_text(encoding="utf-8"))
        missing = sorted(s for s in sources if s not in cat)
        unused = sorted(s for s in cat if s not in sources)
        bad = sorted(s for s in sources & set(cat)
                     if set(re.findall(r"\{(\w+)\}", s)) != set(re.findall(r"\{(\w+)\}", cat[s])))
        print(f"{cat_path.name}: {len(sources)} strings, {len(missing)} missing, {len(unused)} unused, "
              f"{len(bad)} with different {{placeholders}}")
        for s in missing:
            print("  missing:", repr(s))
        for s in bad:
            print("  placeholders differ:", repr(s))
        for s in unused:
            print("  unused: ", repr(s))
        failed |= bool(missing or bad)
        if "--add" in sys.argv and missing:
            cat.update({s: "TODO " + s for s in missing})
            cat_path.write_text(json.dumps(dict(sorted(cat.items())), ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
