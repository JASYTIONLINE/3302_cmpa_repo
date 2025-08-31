# ---
# title: "sc-monitoring-controlling-link-check"
# date: 2025-08-29
# draft: false
# tags: [script, automation, monitoring, controlling]
# function: "D8-Monitoring-Control"
# shortcode: "[sc]" script
# classification: "public"
# retention: "permanent"
# integrityCheck: true
# ---
#
# Purpose:
#   This script automates the Monitoring & Controlling procedure  link chak
#   for closed-loop navigation checks between index and readme files.
#
# Placement:
#   Store in /70-scripts/ at repo core.
#
# Relation:
#   #   This file is the automation tool (script)  that executes that moniotor and control procedure "-link-check" defined in D8-Monitoring-Control.



#!/usr/bin/env python3
import re, os, sys
from pathlib import Path

ROOT = Path(".")  # run from repo root
CONTENT_HINTS = {"index", "readme"}  # implicit .md targets

# Regex for Obsidian wikilinks and Markdown links
WIKI_RE = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")
MD_RE   = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

def norm_target(src_file: Path, target: str) -> Path:
    """
    Normalize link targets to filesystem paths:
    - 'readme' => 'readme.md'
    - 'D0-Compliance/index' => 'D0-Compliance/index.md'
    - '../index' => '../index.md'
    - Keep '.md' if already present; ignore 'http(s)://' links.
    """
    if target.startswith("http://") or target.startswith("https://"):
        return None
    # strip leading './'
    target = target.lstrip("./")
    # resolve relative to the source file directory
    base = src_file.parent
    p = (base / target).resolve()
    # add .md if no suffix and last segment hints a markdown note
    if p.suffix == "":
        if p.name.lower() in CONTENT_HINTS or "/" in target or "\\" in target:
            p = p.with_suffix(".md")
        else:
            # treat bare file without suffix as markdown by default
            p = p.with_suffix(".md")
    return p

def find_links(md: str):
    wikilinks = WIKI_RE.findall(md)
    mdlinks = [m for m in MD_RE.findall(md) if not m.startswith("#")]
    return wikilinks, mdlinks

def is_md_file(path: Path) -> bool:
    return path.suffix.lower() == ".md"

def walk_md(root: Path):
    for p in root.rglob("*.md"):
        # ignore hidden dirs like .git, .obsidian, 90-archive etc. if desired
        parts = {q.name for q in p.parents}
        if ".git" in parts or ".obsidian" in parts or "90-archive" in parts:
            continue
        yield p

def check_closed_loop(root_index: Path):
    """
    Minimal closed-loop contract for each Delta Lane X:
      Home: contents/index.md
      Lane: contents/DX-*/index.md
      README: contents/DX-*/readme.md

    Verify edges:
      Home -> Lane index
      Lane index -> README
      README -> Home
    """
    issues = []
    if not root_index.exists():
        return [f"[LOOP] Missing Home index: {root_index}"]

    # Collect lanes by finding */index.md under contents/
    lanes = sorted((root_index.parent).glob("D*-*/index.md"))
    for lane_idx in lanes:
        lane_dir = lane_idx.parent
        lane_readme = lane_dir / "readme.md"

        # 1) Home contains link to lane index?
        home_txt = root_index.read_text(encoding="utf-8", errors="ignore")
        home_has = f"]({lane_idx.relative_to(root_index.parent)})" in home_txt or \
                   f"[[{lane_idx.relative_to(root_index.parent).with_suffix('')}" in home_txt
        if not home_has:
            issues.append(f"[LOOP] Home lacks link to {lane_idx.relative_to(root_index.parent)}")

        # 2) Lane index links to its readme?
        if lane_idx.exists():
            ltxt = lane_idx.read_text(encoding="utf-8", errors="ignore")
            lane_has = "](" in ltxt and "(readme" in ltxt or "[[readme" in ltxt
            if not lane_has:
                issues.append(f"[LOOP] Lane index lacks link to its readme: {lane_readme}")
        else:
            issues.append(f"[LOOP] Missing lane index: {lane_idx}")

        # 3) Lane readme links back to Home?
        if lane_readme.exists():
            rtxt = lane_readme.read_text(encoding="utf-8", errors="ignore")
            back_home = "]("../ in rtxt and "(../index" in rtxt or "[[../index" in rtxt
            if not back_home:
                issues.append(f"[LOOP] Lane readme lacks back-link to Home: {root_index}")
        else:
            issues.append(f"[LOOP] Missing lane readme: {lane_readme}")
    return issues

def main():
    errors = []
    for md_path in walk_md(ROOT):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        wikilinks, hlinks = find_links(text)

        # Check wikilinks
        for wl in wikilinks:
            tgt = norm_target(md_path, wl)
            if tgt and not tgt.exists():
                errors.append(f"[MISSING] {md_path} → [[{wl}]] → {tgt}")

        # Check markdown links (relative, not http)
        for hl in hlinks:
            if hl.startswith(("http://", "https://")):
                continue
            tgt = norm_target(md_path, hl)
            if tgt and not tgt.exists():
                errors.append(f"[MISSING] {md_path} → ({hl}) → {tgt}")

    # Closed-loop contract
    home_index = Path("contents/index.md")
    if home_index.exists():
        errors.extend(check_closed_loop(home_index))

    if errors:
        print("\n".join(sorted(set(errors))))
        sys.exit(1)
    else:
        print("OK: all links resolve; closed-loop navigation verified.")

if __name__ == "__main__":
    main()
