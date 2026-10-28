"""Les traductions : mêmes clés et mêmes variables dans les 5 langues, et
aucune clé utilisée par le code qui manquerait (sinon Discord affiche la clé
brute, par exemple « clan.war_btn_round », à la place du texte)."""

import ast
import json
import re
import string
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("fr", "en", "es", "de", "ko")
SKIP_DIRS = {"venv", ".venv", "__pycache__", "graphify-out", ".claude", ".git", "tests"}


def flat(data, prefix=""):
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(flat(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def code_files():
    for path in ROOT.rglob("*.py"):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            yield path


class LocalesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.locales = {
            lang: flat(json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8")))
            for lang in LANGS
        }
        cls.code = "\n".join(path.read_text(encoding="utf-8-sig") for path in code_files())
        cls.namespaces = sorted({key.split(".")[0] for key in cls.locales["fr"]})

    def test_same_keys_in_every_language(self):
        reference = set(self.locales["fr"])
        for lang in LANGS[1:]:
            with self.subTest(lang=lang):
                self.assertEqual(sorted(set(self.locales[lang]) ^ reference), [])

    def test_same_variables_in_every_language(self):
        mismatches = []
        for key, text in self.locales["fr"].items():
            expected = set(re.findall(r"{(\w+)}", str(text)))
            for lang in LANGS[1:]:
                found = set(re.findall(r"{(\w+)}", str(self.locales[lang].get(key, ""))))
                if found != expected:
                    mismatches.append(f"{lang}:{key}")
        self.assertEqual(mismatches, [])

    def test_keys_written_in_code_exist(self):
        pattern = r"[\"']((?:%s)\.[A-Za-z0-9_.]+)[\"']" % "|".join(map(re.escape, self.namespaces))
        used = {key for key in re.findall(pattern, self.code)
                if not re.search(r"\.(py|json|md|mp3|log|txt)$", key)}
        known = self.locales["fr"]
        missing = sorted(key for key in used
                         if key not in known and not any(k.startswith(key + ".") for k in known))
        self.assertEqual(missing, [])

    def test_every_text_formats(self):
        broken = []
        for lang in LANGS:
            for key, text in self.locales[lang].items():
                names = {name for _, name, _, _ in string.Formatter().parse(str(text)) if name}
                try:
                    str(text).format(**{name: "x" for name in names})
                except (ValueError, KeyError, IndexError):
                    broken.append(f"{lang}:{key}")
        self.assertEqual(broken, [])

    def test_calls_give_every_variable(self):
        """Une variable oubliée ne plante pas : t() renvoie le texte avec
        « {player} » affiché tel quel. Seul ce test le voit."""
        missing = []
        for path in code_files():
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("t", "t_in")
                        and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)):
                    continue
                key = node.args[1].value
                if key not in self.locales["fr"] or any(kw.arg is None for kw in node.keywords):
                    continue
                given = {kw.arg for kw in node.keywords}
                parent = parents.get(node)
                if isinstance(parent, ast.Attribute) and parent.attr == "format":
                    given |= {kw.arg for kw in parents[parent].keywords}
                needed = set().union(*(
                    {name for _, name, _, _ in string.Formatter().parse(str(self.locales[lang][key])) if name}
                    for lang in LANGS))
                if needed - given:
                    missing.append(f"{path.name}:{node.lineno} {key} {sorted(needed - given)}")
        self.assertEqual(missing, [])

    def test_keys_built_on_the_fly_exist(self):
        pattern = r"t(?:_in)?\(\s*[^,()]+,\s*f[\"']((?:%s)\.[^\"']+)[\"']" % "|".join(map(re.escape, self.namespaces))
        broken = []
        for template in set(re.findall(pattern, self.code)):
            regex = re.compile("^" + re.sub(r"\\\{[^}]*\\\}", ".+", re.escape(template)) + "$")
            if not any(regex.match(key) for key in self.locales["fr"]):
                broken.append(template)
        self.assertEqual(sorted(broken), [])


if __name__ == "__main__":
    unittest.main()
