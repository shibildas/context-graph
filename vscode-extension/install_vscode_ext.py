#!/usr/bin/env python3
"""
One-command installer & VSIX packager for the Context Graph VS Code Extension (`context-graph-vscode`).
1. Bundles the Python SQLite backend (`server/` & `scripts/`) into `vscode-extension/backend/`.
2. Builds a ready-to-distribute `context-graph-vscode-<version>.vsix` package in `vscode-extension/`.
3. Installs the extension directly into any detected VS Code-compatible IDE on macOS, Linux, or Windows:
   - VS Code (`~/.vscode/extensions/`)
   - Cursor (`~/.cursor/extensions/`)
   - Windsurf (`~/.windsurf/extensions/`)
   - Google Antigravity IDE (`~/.antigravity/extensions/`)

Usage:
  python3 vscode-extension/install_vscode_ext.py
"""

import json
import os
import shutil
import zipfile


EXT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(EXT_DIR)

IDE_EXTENSION_ROOTS = [
    ("VS Code", os.path.expanduser("~/.vscode/extensions")),
    ("Cursor", os.path.expanduser("~/.cursor/extensions")),
    ("Windsurf", os.path.expanduser("~/.windsurf/extensions")),
    ("Antigravity IDE", os.path.expanduser("~/.antigravity/extensions")),
]

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".py" ContentType="text/x-python"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".svg" ContentType="image/svg+xml"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""


def build_vsix_manifest(pkg: dict) -> str:
    publisher = pkg.get("publisher", "shibildas")
    name = pkg.get("name", "context-graph-vscode")
    version = pkg.get("version", "1.3.0")
    display_name = pkg.get("displayName", "Context Graph & Query Cache").replace("&", "&amp;")
    desc = pkg.get("description", "").replace("&", "&amp;")
    tags = ",".join(pkg.get("keywords", []))
    categories = ",".join(pkg.get("categories", ["AI"]))
    repo_url = (pkg.get("repository") or {}).get("url", "https://github.com/shibildas/context-graph.git")

    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}" />
    <DisplayName>{display_name}</DisplayName>
    <Description xml:space="preserve">{desc}</Description>
    <Tags>{tags}</Tags>
    <Categories>{categories}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.85.0" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Services.Links.Source" Value="{repo_url}" />
      <Property Id="Microsoft.VisualStudio.Services.Links.Getstarted" Value="{repo_url}" />
      <Property Id="Microsoft.VisualStudio.Services.Links.GitHub" Value="{repo_url}" />
    </Properties>
    <License>extension/LICENSE</License>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def bundle_backend_into(target_ext_dir: str) -> None:
    backend_dir = os.path.join(target_ext_dir, "backend")
    for sub in ("server", "scripts"):
        src = os.path.join(REPO_ROOT, sub)
        dst = os.path.join(backend_dir, sub)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def build_vsix_package(pkg: dict) -> str:
    name = pkg.get("name", "context-graph-vscode")
    version = pkg.get("version", "1.3.0")
    vsix_path = os.path.join(EXT_DIR, f"{name}-{version}.vsix")

    with zipfile.ZipFile(vsix_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML.strip())
        zf.writestr("extension.vsixmanifest", build_vsix_manifest(pkg).strip())

        for item in ("package.json", "extension.js", "README.md", "LICENSE"):
            src = os.path.join(EXT_DIR, item)
            if os.path.isfile(src):
                zf.write(src, f"extension/{item}")

        for subdir in ("media", "backend"):
            sub_root = os.path.join(EXT_DIR, subdir)
            if os.path.isdir(sub_root):
                for root, _, files in os.walk(sub_root):
                    for fname in files:
                        if fname.endswith(".pyc") or "__pycache__" in root:
                            continue
                        abs_p = os.path.join(root, fname)
                        rel_p = os.path.relpath(abs_p, EXT_DIR).replace(os.sep, "/")
                        zf.write(abs_p, f"extension/{rel_p}")

    print(f"[OK] Built VSIX package: {vsix_path}")
    return vsix_path


def install_to_dir(ide_name: str, ext_root: str, folder_name: str) -> str:
    os.makedirs(ext_root, exist_ok=True)
    dest = os.path.join(ext_root, folder_name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    for item in ("package.json", "extension.js", "README.md", "LICENSE"):
        src_file = os.path.join(EXT_DIR, item)
        if os.path.isfile(src_file):
            shutil.copy2(src_file, os.path.join(dest, item))

    media_src = os.path.join(EXT_DIR, "media")
    if os.path.isdir(media_src):
        shutil.copytree(media_src, os.path.join(dest, "media"))

    bundle_backend_into(dest)
    print(f"[OK] Installed into {ide_name}: {dest}")
    return dest


def main() -> None:
    with open(os.path.join(EXT_DIR, "package.json"), "r", encoding="utf-8") as f:
        pkg = json.load(f)

    publisher = pkg.get("publisher", "shibildas")
    name = pkg.get("name", "context-graph-vscode")
    version = pkg.get("version", "1.3.0")
    folder_name = f"{publisher}.{name}-{version}"

    # 1. Bundle backend inside ./vscode-extension/backend
    bundle_backend_into(EXT_DIR)

    # 2. Build ready-to-publish .vsix archive
    build_vsix_package(pkg)

    # 3. Install into local IDEs
    installed_any = False
    for ide_name, root in IDE_EXTENSION_ROOTS:
        parent = os.path.dirname(root)
        if os.path.isdir(parent) or os.path.isdir(root):
            install_to_dir(ide_name, root, folder_name)
            installed_any = True

    if not installed_any:
        default_root = os.path.expanduser("~/.vscode/extensions")
        install_to_dir("VS Code (created ~/.vscode/extensions)", default_root, folder_name)

    print("\nReload your IDE window (`Developer: Reload Window`) to activate Context Graph & Query Cache.")


if __name__ == "__main__":
    main()
