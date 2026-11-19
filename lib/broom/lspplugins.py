"""Which enabled Claude Code plugins start a language server for files broom's own `.lsp.json` serves.

Claude Code starts one server per file extension, so a plugin claiming an extension of broom's silently replaces its
server. What a plugin claims is read from its own declaration (its `plugin.json`, its `.lsp.json`, or its entry in its
marketplace), never from its name; a plugin whose declaration can't be found is judged by `LSP_PLUGINS`, a list of
names."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .lsp import servers
from .state import load_json

# Plugins known to start a language server for the same files as broom's, for when their declaration can't be read.
LSP_PLUGINS = {"gopls-lsp": "go", "gopls": "go", "typescript-lsp": "js", "vtsls": "js", "ts7-lsp": "js",
               "typescript-language-server": "js", "rust-analyzer-lsp": "rust", "rust-analyzer": "rust",
               "pyright-lsp": "py", "pyright": "py", "swift-lsp": "swift", "sourcekit-lsp": "swift"}
# broom's language of each language id its .lsp.json serves.
BY_LANGUAGE_ID = {"go": "go", "typescript": "js", "typescriptreact": "js", "javascript": "js", "javascriptreact": "js",
                  "rust": "rust", "python": "py", "swift": "swift", "css": "css", "scss": "css", "less": "css"}


def broom_languages() -> Dict[str, str]:
    """Each file extension broom's language servers serve, with the language it counts for."""
    return {ext: BY_LANGUAGE_ID[language] for ext, (_, language) in servers().items() if language in BY_LANGUAGE_ID}


def config_dir() -> Path:
    """Claude Code's configuration folder."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def declared(spec: object, base: Path) -> Optional[Set[str]]:
    """The extensions that the `lspServers` value `spec` claims: an object of servers, a path (from `base`) to a JSON
    file of them, or a list of either. None when nothing could be read from it."""
    if isinstance(spec, str):
        return declared(load_json(base / spec, None), base)
    if isinstance(spec, list):
        found = [declared(one, base) for one in spec]
        return set().union(*(f for f in found if f)) if any(f is not None for f in found) else None
    if not isinstance(spec, dict):
        return None
    return {ext for server in spec.values() if isinstance(server, dict)
            for ext in (server.get("extensionToLanguage") or {})}


def folder_claims(folder: Path) -> Optional[Set[str]]:
    """The extensions a plugin folder declares, in its `plugin.json` and its `.lsp.json`; None when it declares none."""
    manifest = load_json(folder / ".claude-plugin" / "plugin.json", {})
    sources = [declared(manifest.get("lspServers") if isinstance(manifest, dict) else None, folder),
               declared(load_json(folder / ".lsp.json", None), folder)]
    found = [s for s in sources if s is not None]
    return set().union(*found) if found else None


def install_folder(key: str, repo: Path) -> Optional[Path]:
    """Where the plugin `key` is installed: its entry for this repo, else the user's, else the first."""
    entries = load_json(config_dir() / "plugins" / "installed_plugins.json", {}).get("plugins", {}).get(key)
    entries = [e for e in entries if isinstance(e, dict) and e.get("installPath")] if isinstance(entries, list) else []
    mine = [e for e in entries if e.get("projectPath") == str(repo)] or [e for e in entries if e.get("scope") == "user"]
    chosen = (mine or entries or [None])[0]
    return Path(chosen["installPath"]) if chosen else None


def marketplace_claims(name: str, marketplace: str) -> Optional[Set[str]]:
    """The extensions the marketplace's entry for plugin `name` declares (the official language server plugins have
    no folder declaration: it is in their marketplace's list); None when it declares none."""
    known = load_json(config_dir() / "plugins" / "known_marketplaces.json", {}).get(marketplace)
    where = known.get("installLocation") if isinstance(known, dict) else None
    if not where:
        return None
    base = Path(where)
    for entry in load_json(base / ".claude-plugin" / "marketplace.json", {}).get("plugins", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return declared(entry.get("lspServers"), base)
    return None


def claims(key: str, repo: Path) -> Optional[Set[str]]:
    """The extensions the enabled plugin `key` ("name@marketplace") claims for a language server; None when its
    declaration can't be found."""
    name, _, marketplace = key.partition("@")
    folder = install_folder(key, repo)
    found = [folder_claims(folder) if folder else None, marketplace_claims(name, marketplace)]
    found = [f for f in found if f is not None]
    return set().union(*found) if found else None


def enabled(settings: List[Path]) -> List[str]:
    """The plugins the settings files enable, each once."""
    keys: Dict[str, None] = {}
    for path in settings:
        plugins = load_json(path, {}).get("enabledPlugins") or {}
        keys.update({key: None for key, on in plugins.items() if on is True})
    return list(keys)


def competing(settings: List[Path], repo: Path) -> List[Tuple[str, str]]:
    """Each enabled plugin that claims an extension broom's servers serve, as (plugin key, broom's language): one pair
    per language it competes for."""
    ours, out = broom_languages(), []
    for key in enabled(settings):
        name = key.split("@")[0]
        if name == "broom":
            continue
        exts = claims(key, repo)
        langs = [LSP_PLUGINS[name]] if exts is None and name in LSP_PLUGINS else list(
            dict.fromkeys(ours[e] for e in sorted(exts or ()) if e in ours))
        out += [(key, lang) for lang in langs]
    return out
