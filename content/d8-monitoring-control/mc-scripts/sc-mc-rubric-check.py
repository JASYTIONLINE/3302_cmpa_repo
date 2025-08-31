#!/usr/bin/env python3
# ---
# shortcode: "[sc] script"
# name: "sc-mc-rubric-check.py"
# version: "1.0.0"
# description: "Rubric/health checker for CMPA 3302 knowledge base assignments. Scans content/ against Assignment 01 requirements and DEIHC guardrails; writes an audit to a-mc-audits/."
# tags: ["DEIHC","KMS","audit","rubric","CMPA3302","monitoring-control"]
# ---

import re
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
AUDIT_SUBPATH = ["content", "d8-monitoring-control", "a-mc-audits"]
MC_SCRIPTS_SUBPATH = ["content", "d8-monitoring-control", "mc-scripts"]

# Assignment rules (can be reused in later assignments)
MIN_CATEGORIES = 5
MAX_CATEGORIES = 7

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")

def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    seen = set()
    while True:
        if cur in seen:
            break
        seen.add(cur)
        if (cur / "content").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit("Error: cannot locate repo root (missing content/ upward).")

def list_md_outside_content(repo_root: Path) -> List[str]:
    out = []
    content_dir = repo_root / "content"
    for dp, dn, fn in os.walk(repo_root):
        here = Path(dp)
        # skip content subtree entirely
        if content_dir in here.parents or here == content_dir:
            continue
        # skip typical noise
        if any(x in here.parts for x in (".git", ".obsidian", "node_modules", "public", ".quartz", "__pycache__")):
            continue
        for f in fn:
            if f.lower().endswith(".md"):
                out.append(str((here / f).resolve().relative_to(repo_root)))
    return out

def parse_frontmatter_title(md: str) -> Tuple[bool, str]:
    """
    Return (has_frontmatter, title_value or "")
    """
    # frontmatter must begin at top with ---
    if not md.startswith("---"):
        return False, ""
    # find closing ---
    m = re.search(r"^---\s*$", md, flags=re.M)  # first line
    # already at start; now find second --- after first line
    closers = list(re.finditer(r"^---\s*$", md, flags=re.M))
    if len(closers) < 2:
        return True, ""  # malformed frontmatter
    fm_end = closers[1].end()
    fm_text = md[:fm_end]
    # extract title: title: ...
    tm = re.search(r"(?im)^\s*title\s*:\s*(.+?)\s*$", fm_text)
    title = tm.group(1).strip() if tm else ""
    return True, title

def extract_wikilinks_to_category_indexes(md: str) -> List[Tuple[str, str]]:
    """
    Returns list of (folder, display_title) from wikilinks like [[folder-name/index|Display Title]]
    """
    # Accept both [[folder/index|Title]] and [[folder/index| Title With Spaces ]]
    pattern = re.compile(r"\[\[([A-Za-z0-9._\-\/]+)/index\|([^\]]+?)\]\]")
    links = pattern.findall(md)
    # Normalize folder (if given as 'folder/index' or with subpaths)
    out = []
    for folder, disp in links:
        # only keep the last path segment as category folder name if subpaths provided
        folder_norm = Path(folder).parts[0] if "/" in folder else folder
        out.append((folder_norm.strip(), disp.strip()))
    return out

def has_main_categories_heading(md: str) -> bool:
    # require a "## Main Categories" heading (case-insensitive, allow leading/trailing spaces)
    return re.search(r"(?im)^\s*##\s+Main Categories\s*$", md) is not None

def is_lower_hyphen(name: str) -> bool:
    return name == name.lower() and " " not in name and re.match(r"^[a-z0-9\-._]+$", name) is not None

# ------------------------------------------------------------
# Checks
# ------------------------------------------------------------
def run_checks(repo_root: Path) -> Dict:
    result = {
        "repo_root": str(repo_root),
        "content_exists": False,
        "main_index_exists": False,
        "main_index_has_heading": False,
        "wikilinks": [],  # (folder, display)
        "category_folders": [],
        "category_folder_issues": [],
        "category_index_issues": [],  # list of dicts per category
        "count_categories": 0,
        "count_outside_md": 0,
        "outside_md_list": [],
        "pitfalls": [],
        "scores": {
            "architectural_logic": "unchecked",
            "technical_implementation": "unchecked",
            "version_control": "not_evaluated"
        },
        "notes": []
    }

    content_dir = repo_root / "content"
    result["content_exists"] = content_dir.is_dir()

    # Pitfall: duplicated or malformed index naming (index.md.md)
    weird = list(content_dir.rglob("index.md.md")) if content_dir.exists() else []
    if weird:
        result["pitfalls"].append("Found files named index.md.md (rename to index.md).")

    # Main index
    main_index = content_dir / "index.md"
    if main_index.exists():
        result["main_index_exists"] = True
        main_text = read_text(main_index)
        result["main_index_has_heading"] = has_main_categories_heading(main_text)
        result["wikilinks"] = extract_wikilinks_to_category_indexes(main_text)
    else:
        result["notes"].append("Missing content/index.md (homepage).")

    # Category folders = immediate children of content (directories only)
    if content_dir.exists():
        for p in sorted([x for x in content_dir.iterdir() if x.is_dir()]):
            result["category_folders"].append(p.name)

    # Count categories (only those that look like categories—exclude special dirs starting with '.' or '_')
    cat_folders = [f for f in result["category_folders"] if not f.startswith(".") and not f.startswith("_")]
    result["count_categories"] = len(cat_folders)

    # Validate category folder names
    for folder in cat_folders:
        if not is_lower_hyphen(folder):
            result["category_folder_issues"].append(f"Folder '{folder}' should be lowercase and hyphenated (no spaces).")

    # For each category folder, require an index.md with title in frontmatter
    for folder in cat_folders:
        idx = content_dir / folder / "index.md"
        if not idx.exists():
            result["category_index_issues"].append({
                "folder": folder,
                "issue": "Missing index.md in category folder."
            })
            continue
        text = read_text(idx)
        has_fm, title = parse_frontmatter_title(text)
        if not has_fm:
            result["category_index_issues"].append({
                "folder": folder,
                "issue": "index.md missing YAML frontmatter."
            })
        elif not title.strip():
            result["category_index_issues"].append({
                "folder": folder,
                "issue": "YAML frontmatter present but missing 'title' property."
            })

    # Compare wikilinks vs category folders
    linked = [f for (f, disp) in result["wikilinks"]]
    unlinked_cats = [f for f in cat_folders if f not in linked]
    missing_folders_from_links = [f for f in linked if f not in cat_folders]
    if unlinked_cats:
        result["notes"].append(f"Categories not linked from homepage: {', '.join(unlinked_cats)}.")
    if missing_folders_from_links:
        result["notes"].append(f"Homepage links refer to non-existent folders: {', '.join(missing_folders_from_links)}.")

    # MD files outside content
    outside = list_md_outside_content(repo_root)
    result["outside_md_list"] = outside
    result["count_outside_md"] = len(outside)
    if outside:
        result["notes"].append("Found Markdown files outside content/ (risk of accidental repo vault usage).")

    # Score logic (simple rubric mapping)
    # Architectural Logic: only what we can objectively test (category count 5–7)
    if MIN_CATEGORIES <= result["count_categories"] <= MAX_CATEGORIES:
        result["scores"]["architectural_logic"] = "meets_minimum"
    else:
        result["scores"]["architectural_logic"] = "needs_attention"

    # Technical Implementation: pass only if no core errors
    tech_ok = (
        result["main_index_exists"]
        and result["main_index_has_heading"]
        and not result["category_folder_issues"]
        and not result["category_index_issues"]
        and not missing_folders_from_links
    )
    result["scores"]["technical_implementation"] = "meets_minimum" if tech_ok else "needs_attention"

    return result

# ------------------------------------------------------------
# Audit writer
# ------------------------------------------------------------
def write_audit(repo_root: Path, data: Dict) -> Path:
    audits = repo_root.joinpath(*AUDIT_SUBPATH)
    ensure_dir(audits)
    out = audits / f"a-rubric-check-{timestamp()}.md"

    lines = []
    # YAML frontmatter for the audit
    lines.append("---\n")
    lines.append('shortcode: "[a] audit"\n')
    lines.append(f'name: "{out.stem}"\n')
    lines.append(f'timestamp: "{datetime.now().isoformat(timespec="seconds")}"\n')
    lines.append(f'repo_root: "{data["repo_root"]}"\n')
    lines.append("totals:\n")
    lines.append(f"  categories: {data['count_categories']}\n")
    lines.append(f"  md_outside_content: {data['count_outside_md']}\n")
    lines.append("scores:\n")
    lines.append(f"  architectural_logic: {data['scores']['architectural_logic']}\n")
    lines.append(f"  technical_implementation: {data['scores']['technical_implementation']}\n")
    lines.append(f"  version_control: {data['scores']['version_control']}\n")
    lines.append("---\n\n")

    lines.append("# Assignment 01 Rubric/Health Check Audit\n\n")
    lines.append(f"- Repo root: `{data['repo_root']}`\n")
    lines.append(f"- content/ exists: `{str(data['content_exists']).lower()}`\n")
    lines.append(f"- main index present (content/index.md): `{str(data['main_index_exists']).lower()}`\n")
    lines.append(f"- main index has '## Main Categories' heading: `{str(data['main_index_has_heading']).lower()}`\n\n")

    lines.append("## Category Folders (top level under content/)\n")
    if data["category_folders"]:
        for f in data["category_folders"]:
            lines.append(f"- `{f}`\n")
    else:
        lines.append("_None_\n")
    lines.append("\n")

    if data["category_folder_issues"]:
        lines.append("## Category Folder Naming Issues\n")
        for iss in data["category_folder_issues"]:
            lines.append(f"- {iss}\n")
        lines.append("\n")

    if data["category_index_issues"]:
        lines.append("## Category Index Issues\n")
        for iss in data["category_index_issues"]:
            lines.append(f"- `{iss['folder']}`: {iss['issue']}\n")
        lines.append("\n")

    lines.append("## Homepage Links (wikilinks to category index)\n")
    if data["wikilinks"]:
        for folder, disp in data["wikilinks"]:
            lines.append(f"- `[[{folder}/index|{disp}]]`\n")
    else:
        lines.append("_None_\n")
    lines.append("\n")

    if data["pitfalls"]:
        lines.append("## Common Pitfalls Detected\n")
        for p in data["pitfalls"]:
            lines.append(f"- {p}\n")
        lines.append("\n")

    if data["outside_md_list"]:
        lines.append("## Markdown Files Found Outside content/\n")
        for p in data["outside_md_list"]:
            lines.append(f"- `{p}`\n")
        lines.append("\n")

    if data["notes"]:
        lines.append("## Notes / Fix Suggestions\n")
        for n in data["notes"]:
            lines.append(f"- {n}\n")
        lines.append("\n")

    lines.append("## Rubric Snapshot\n")
    lines.append(f"- Architectural Logic (5–7 categories): **{data['scores']['architectural_logic']}**\n")
    lines.append(f"- Technical Implementation (files, names, links): **{data['scores']['technical_implementation']}**\n")
    lines.append("- Version Control Practices: **not evaluated** (commit message crafted in chat before push)\n")

    write_text(out, "".join(lines))
    return out

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    # Find repo root from current working directory
    repo_root = find_repo_root(Path.cwd())
    data = run_checks(repo_root)
    audit_path = write_audit(repo_root, data)

    # Console summary
    print("[mc] Rubric/health check complete.")
    print(f"      Categories: {data['count_categories']}  |  Outside MD: {data['count_outside_md']}")
    print(f"      Scores -> Architectural: {data['scores']['architectural_logic']}, Technical: {data['scores']['technical_implementation']}")
    print(f"[a]   Audit written: {audit_path}")

if __name__ == "__main__":
    main()
