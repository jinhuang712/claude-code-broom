"""The links of a Markdown file as its structure gives them: a link, an image and a definition count; a link in fenced
code, a code span, a comment or a tag does not. And what a destination points at, against the files of a repo."""

from __future__ import annotations

import unittest

from support import BroomCase

from broom import mdlinks


def text(*rows: str) -> str:
    """A file's text from its lines."""
    return "\n".join(rows) + "\n"


class LinksTest(BroomCase):
    def test_links_images_and_definitions_with_the_line_they_start_on(self) -> None:
        found = mdlinks.links(text("# T", "[a](a.md) and ![img](img/x.png \"title\") and [b](<my file.md>)",
                                   "[multi", "line](ml.md)", "[ref]: ref.md 'Title'", "[![badge](b.svg)](c.md)"))
        self.assertEqual(found, [(2, "a.md"), (2, "img/x.png"), (2, "my file.md"), (3, "ml.md"), (5, "ref.md"),
                                 (6, "c.md"), (6, "b.svg")])

    def test_what_markdown_does_not_make_a_link_of_is_none(self) -> None:
        found = mdlinks.links(text("`[a](a.md)` and ``[b](b.md)`` and \\[c](c.md)", "```", "[d](d.md)", "```",
                                   "~~~sh", "[e](e.md)", "~~~~", "<!-- [f](f.md) -->", '<a href="[g](g.md)">x</a>',
                                   "> - ```", ">   [h](h.md)", ">   ```", "[^1]: a note", "[i](i.md)"))
        self.assertEqual(found, [(14, "i.md")])

    def test_a_destination_with_brackets_a_title_or_escapes(self) -> None:
        found = mdlinks.links(text("[a](d(1).md) [b [nested]](n.md) [c](c.md \"t\") [d](d\\_x.md) [e]()", "[f](f.md",
                                   "[g](g.md) `unclosed"))
        self.assertEqual(found, [(1, "d(1).md"), (1, "n.md"), (1, "c.md"), (1, "d_x.md"), (1, ""), (3, "g.md")])

    def test_a_blank_line_ends_a_code_span_and_a_link_text(self) -> None:
        found = mdlinks.links(text("a ` b", "", "[c](c.md) `", "", "[d", "", "e](e.md)"))
        self.assertEqual(found, [(3, "c.md")])


class TargetTest(BroomCase):
    def test_only_a_relative_path_is_a_target_and_it_is_read_from_the_file_that_holds_it(self) -> None:
        for dest in ("", "#top", "https://x.org/a", "mailto:a@b.c", "//host/a", "/from/the/site/root", "?q=1"):
            self.assertIsNone(mdlinks.target(dest, "docs/a.md"), dest)
        self.assertEqual(mdlinks.target("b.md#sec", "docs/a.md"), "docs/b.md")
        self.assertEqual(mdlinks.target("../README.md?x=1", "docs/a.md"), "README.md")
        self.assertEqual(mdlinks.target("my%20file.md", "a.md"), "my file.md")
        self.assertEqual(mdlinks.target("../x.md", "a.md"), "../x.md", "out of the repo: no file of it")
        self.assertEqual(mdlinks.target("./", "docs/a.md"), "docs")

    def test_a_link_is_broken_when_no_file_or_folder_of_the_repo_is_there(self) -> None:
        known = mdlinks.known_paths(["README.md", "docs/a.md", "docs/img/x.png"])
        body = text("[ok](docs/a.md) [folder](docs/img/) [root](.) [anchor](#a) [url](https://x.org/y.md)",
                    "[gone](docs/gone.md) [case](DOCS/a.md) ![pic](docs/img/y.png)", "[ref]: nowhere/at/all.md")
        self.assertEqual(mdlinks.broken("README.md", body, known), [2, 2, 2, 3])


if __name__ == "__main__":
    unittest.main()
