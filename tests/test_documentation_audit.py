"""Protect navigable documentation and the installer instructions it exposes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote
import unittest

ROOT = Path(__file__).resolve().parents[1]


def heading_ids(text):
    result = set()
    seen = {}
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            run, suffix = marker.groups()
            if not fence:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not suffix.strip():
                fence = ""
            continue
        if fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+)", line)
        if not match:
            continue
        title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", match[1]).strip().strip("#").strip().lower()
        slug = "".join(c for c in title if unicodedata.category(c)[0] in "LN" or c in " _-").replace(" ", "-")
        number = seen.get(slug, 0)
        seen[slug] = number + 1
        result.add(slug + (f"-{number}" if number else ""))
    return result


class DocumentationAuditTests(unittest.TestCase):
    def test_local_markdown_links_resolve_and_fragments_reach_existing_headings(self):
        documents = [ROOT / "README.md", *sorted((ROOT / "skills").rglob("*.md"))]
        headings = {p.resolve(): heading_ids(p.read_text(encoding="utf-8")) for p in documents}
        for path in documents:
            for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("//"):
                    continue
                local, separator, fragment = target.partition("#")
                local = unquote(local)
                destination = (path.parent / local).resolve() if local else path.resolve()
                with self.subTest(source=str(path.relative_to(ROOT)), target=target):
                    self.assertTrue(destination.is_file(), f"missing Markdown target: {destination}")
                    if separator:
                        self.assertIn(unquote(fragment), headings.get(destination, set()))

    def test_release_helper_documents_its_actual_activation_line(self):
        path = ROOT / "skills/lean-stack/scripts/install_plugin.py"
        spec = importlib.util.spec_from_file_location("documented_install_helper", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        versioning = (ROOT / "skills/lean-stack/references/versioning.md").read_text(encoding="utf-8")
        self.assertIn(module.DEFAULT_INVOCATION_LINE, versioning)
        self.assertIn("AGENTS.override.md", versioning)
        self.assertIn("--codex-home", versioning)
        # Native calls must carry bounded history; task text cannot replace the parameters.
        for relative in (
            "SKILL.md",
            "references/dispatch-start.md",
            "references/collaboration.md",
        ):
            source = (ROOT / "skills/lean-stack" / relative).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"因(?:无法|不能)\s*同时显式覆盖")
        native_contract = "\n".join(
            (ROOT / "skills/lean-stack" / relative).read_text(encoding="utf-8")
            for relative in ("SKILL.md", "references/dispatch-start.md")
        )
        self.assertIn('fork_turns="none"', native_contract)
        self.assertIn('禁止 `fork_turns="all"`', native_contract)
        self.assertIn("原生参数", native_contract)


if __name__ == "__main__":
    unittest.main()
