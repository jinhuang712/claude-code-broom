"""CSS, SCSS and Less: broom's stylelint defaults, a project's own config, rules as functions."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from support import (
    HAS_CSS_LSP, HAS_STYLELINT,
    BroomCase,
)


def stylelint_modules(config: str):
    """The node_modules the stylelint on PATH lives in, when it also holds `config`, a dialect config broom's
    defaults extend: a test repo links it in, since stylelint loads that config from the project."""
    exe = shutil.which("stylelint")
    mods = Path(exe).resolve().parents[2] if exe else None  # node_modules/stylelint/bin/stylelint.mjs
    return mods if mods and (mods / config).is_dir() else None
SCSS_MODULES = stylelint_modules("stylelint-config-recommended-scss")
LESS_MODULES = stylelint_modules("stylelint-config-recommended-less")
CSS_TAILWIND = """@import "tailwindcss";
@theme {
  --color-brand: oklch(0.72 0.11 221);
}
.btn {
  @apply rounded-lg px-4;
  composes: base from "./base.module.css";
  color: --alpha(var(--color-brand) / 50%);
}
:global(.dark) .btn {
  color: white;
}
"""
SCSS_SASS = """@use "sass:math";
$w: 10px;
@mixin pad($p) {
  padding: $p;
}
.a {
  width: math.div($w, 2);
  @include pad(4px);
  &__b {
    color: red;
  }
}
@each $n in 1, 2 {
  .m-#{$n} {
    margin: #{$n * 4}px;
  }
}
"""
LESS_ANTD = """@import (reference) "./theme.less";
@primary: #1890ff;
@prefix: ~"app";
.mixin(@color; @padding: 2px) {
  color: @color;
  padding: @padding;
}
.@{prefix}-card {
  .mixin(#fff; 4px);
  color: fade(@primary, 50%);
  width: ~"calc(100% - 16px)";
  &:extend(.base all);
  :global(.ant-card-head) {
    border: 0;
  }
}
"""
CSS_TYPO = ".bad {\n  colr: red;\n}\n"


class CssTest(BroomCase):
    # CSS

    def css_repo(self, files: dict = None) -> Path:
        return self.repo({"package.json": '{"name":"c","private":true}\n', ".gitignore": "node_modules\n",
                          **(files or {})})

    @unittest.skipUnless(HAS_STYLELINT, "stylelint missing")
    def test_css_defaults_block_mistakes_but_accept_tailwind_and_css_modules(self) -> None:
        r = self.css_repo()
        (r / "src").mkdir()
        (r / "src/app.css").write_text(CSS_TAILWIND + CSS_TYPO)  # new, so every line counts
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m css"))
        self.assertIn('src/app.css:14:3  property-no-unknown  Unknown property "colr"', reason)
        self.assertIn("blocked: 1 issue(s)", reason, "nothing from Tailwind or CSS modules")

    @unittest.skipUnless(HAS_STYLELINT, "stylelint missing")
    def test_css_defaults_skip_build_output_and_minified_files(self) -> None:
        r = self.css_repo()
        for name in ("dist/app.css", "packages/ui/build/ui.css", "public/vendor.min.css"):
            (r / name).parent.mkdir(parents=True, exist_ok=True)
            (r / name).write_text(".a{colr:red}.b{}\n")
        self.sh(r, "git", "add", "-f", "-A")
        self.assertEqual(self.denied(self.commit(r, "git commit -m built")), "")

    @unittest.skipUnless(SCSS_MODULES, "stylelint-config-recommended-scss missing")
    def test_scss_defaults_know_sass(self) -> None:
        r = self.css_repo()
        (r / "node_modules").symlink_to(SCSS_MODULES)
        (r / "theme.scss").write_text(SCSS_SASS + CSS_TYPO)
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m scss"))
        self.assertIn('theme.scss:19:3  property-no-unknown  Unknown property "colr"', reason)
        self.assertIn("blocked: 1 issue(s)", reason, "nothing from Sass itself")

    @unittest.skipUnless(LESS_MODULES, "stylelint-config-recommended-less missing")
    def test_less_defaults_know_less_and_css_modules(self) -> None:
        r = self.css_repo()
        (r / "node_modules").symlink_to(LESS_MODULES)
        (r / "Card.module.less").write_text(LESS_ANTD + CSS_TYPO)
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m less"))
        self.assertIn('Card.module.less:18:3  property-no-unknown  Unknown property "colr"', reason)
        self.assertIn("blocked: 1 issue(s)", reason, "nothing from Less itself")

    @unittest.skipUnless(HAS_STYLELINT, "stylelint missing")
    def test_dialects_without_their_defaults_are_skipped_with_a_note(self) -> None:
        r = self.css_repo()
        (r / "theme.scss").write_text(SCSS_SASS + CSS_TYPO)
        (r / "theme.less").write_text(LESS_ANTD + CSS_TYPO)
        self.sh(r, "git", "add", "-A")
        out = self.commit(r, "git commit -m styles")
        self.assertEqual(self.denied(out), "")
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("stylelint-config-recommended-scss", context)
        self.assertIn("stylelint-config-recommended-less", context)
        self.assertIn("/broom:setup", context)

    @unittest.skipUnless(HAS_STYLELINT, "stylelint missing")
    def test_a_projects_stylelint_config_replaces_the_defaults(self) -> None:
        r = self.repo({"package.json": '{"name":"c","private":true,"stylelint":{"rules":{"color-no-hex":true}}}\n'})
        (r / "a.css").write_text(".a {\n  color: #fff;\n  colr: red;\n}\n")
        self.sh(r, "git", "add", "-A")
        reason = self.denied(self.commit(r, "git commit -m css"))
        self.assertIn("color-no-hex", reason)
        self.assertNotIn("colr", reason)

    def test_css_linters_follow_the_nearest_config(self) -> None:
        from broom.toolchain import css_linters

        r = self.repo({"package.json": "{}\n", "biome.json": "{}\n",
                       "web/package.json": '{"devDependencies": {"@eslint/css": "^1"}}\n',
                       "web/eslint.config.js": "export default [];\n", "lib/.stylelintrc.json": "{}\n"})
        def tools(p: str) -> list:
            return [(t, str(d.relative_to(r)) if d != r else ".") for t, d in css_linters(r / p, r)]

        self.assertEqual(tools("a.css"), [("biome", ".")])
        self.assertEqual(tools("a.scss"), [("stylelint-default", ".")], "biome doesn't read SCSS")
        self.assertEqual(tools("web/a.css"), [("eslint", "web")])
        self.assertEqual(tools("web/a.scss"), [("stylelint-default", "web")], "nor does @eslint/css")
        self.assertEqual(tools("a.less"), [("stylelint-default", ".")], "nor Less")
        self.assertEqual(tools("lib/a.scss"), [("stylelint", "lib")])

    def test_css_function_scope_widens_to_the_innermost_rule(self) -> None:
        from broom.lsp import css_rules, expand_to_functions

        def sym(kind: int, first: int, last: int, *children: dict) -> dict:
            return {"kind": kind, "children": list(children), "range": {
                "start": {"line": first - 1, "character": 0}, "end": {"line": last - 1, "character": 1}}}

        # .a (1-6) nesting &__b (3-4); @media (8-10) holding .c (9); a Sass variable (12)
        ranges = css_rules([sym(5, 1, 6, sym(5, 3, 4)), sym(2, 8, 10, sym(5, 9, 9)), sym(13, 12, 12)])
        self.assertEqual(sorted(ranges), [(1, 6), (3, 4), (9, 9)])
        self.assertEqual(expand_to_functions({3}, ranges), {3, 4}, "the nested rule, not its parent")
        self.assertEqual(expand_to_functions({2}, ranges), set(range(1, 7)))
        self.assertEqual(expand_to_functions({9, 12}, ranges), {9, 12})

    @unittest.skipUnless(HAS_CSS_LSP, "vscode-css-language-server or oxfmt missing")
    def test_function_scope_with_the_css_language_server(self) -> None:
        src = ".a {\n  color:red;\n  margin:0;\n}\n.b {\n  color:blue;\n}\n"
        r = self.repo({".oxfmtrc.json": "{}\n", "a.css": src})
        (r / "a.css").write_text(src.replace("margin:0", "margin:1px"))
        self.cli(r, "fmt", "--scope", "function")
        text = (r / "a.css").read_text()
        self.assertIn("  color: red;\n  margin: 1px;\n", text, "the changed rule is formatted")
        self.assertIn("  color:blue;\n", text, "the untouched rule is not")

    def test_doctor_finds_css_at_any_depth_inside_and_outside_js_projects(self) -> None:
        r = self.repo({"go.mod": "module example.com/m\n\ngo 1.26\n", "static/app.css": ".a {}\n",
                       "static/app.min.css": ".a{}\n", "web/package.json": '{"name":"w","private":true}\n',
                       "web/src/components/card/card.module.scss": "$a: 1px;\n", "web/dist/out.css": ".a {}\n",
                       "web/src/theme.less": "@a: 1px;\n"})
        result = self.doctor(r, self.fake_path(keep=("go", "gofmt")))
        self.assertEqual(result["languages"]["css"], [".", "web"])
        self.assertEqual(result["languages"]["scss"], ["web"])
        self.assertEqual(result["languages"]["less"], ["web"])
        self.assertIn("npm i -g stylelint", result["fix"])
        self.assertIn("npm i -g vscode-langservers-extracted", result["fix"])
        web = next(c for c in result["fix"] if c.startswith("cd web && npm i -D")).split()
        self.assertIn("stylelint", web)
        self.assertIn("stylelint-config-recommended-scss", web)
        self.assertIn("stylelint-config-recommended-less", web)
        self.assertIn("broom init .", result["configure"], "the Go service's CSS has no formatter")
        out = self.cli(r, "init").stdout
        self.assertIn(".oxfmtrc.json", out)
        self.assertFalse(list(r.glob(".stylelintrc*")), "broom's stylelint defaults need no config file")
