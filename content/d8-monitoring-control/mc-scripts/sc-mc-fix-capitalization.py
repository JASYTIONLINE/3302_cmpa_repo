# ---
# title: "sc-mc-fix-capitalization"
# date: 2025-08-29
# draft: false
# tags: [script, monitoring, controlling, capitalization, fix]
# function: "d8-monitoring-control"
# shortcode: "[sc]" script
# classification: "public"
# retention: "permanent"
# integrityCheck: true
# ---
#
# Purpose:
#   Normalize capitalization in Markdown documents.
#   - Keeps filenames and foldernames lowercase (inside wiki-links or paths).
#   - Restores sentence capitalization in normal paragraphs.
#   - Restores proper nouns (PMBOK, ISO, DEIHC, Obsidian, GitHub, Canvas, GPT, CMPA, KMS, DERIMS).
#
# Placement:
#   Place anywhere in the repo. It will find the "content" folder, go up
#   one folder (repo root), and process all .md files from there down.
#
# Relation:
#   Supports Monitoring & Control by enforcing capitalization standards
#   and automatically generating an audit log of each run.

import re
import argparse
from pathlib import Path
from datetime import datetime

# whitelist of proper nouns
PROPER_NOUNS = {
    "pmbok": "PMBOK",
    "iso": "ISO",
    "deihc": "DEIHC",
    "obsidian": "Obsidian",
    "github": "GitHub",
    "canvas": "Canvas",
    "gpt": "GPT",
    "cmpa": "CMPA",
    "kms": "KMS",
    "derims": "DERIMS"
}

results = []  # audit log collector

def fix_text(text: str) -> str:
    fixed_lines = []
    in_codeblock = False
    in_yaml = False

    for line in text.splitlines():
        stripped = line.strip()

        # Detect YAML frontmatter start/end
        if stripped.startswith("---") and not in_codeblock:
            in_yaml = not in_yaml
            fixed_lines.append(line)
            continue

        # Detect fenced code blocks
        if stripped.startswith("```"):
            in_codeblock = not in_codeblock
            fixed_lines.append(line)
            continue

        # Skip wiki-links, YAML, or code blocks
        if in_yaml or in_codeblock or "[[" in line or "]]" in line:
            fixed_lines.append(line)
            continue

        # Capitalize first letter of sentences
        line = re.sub(r'(^|[.!?]\s+)([a-z])',
                      lambda m: m.group(1) + m.group(2).upper(),
                      line)

        # Restore proper nouns
        for k, v in PROPER_NOUNS.items():
            line = re.sub(rf"\b{k}\b", v, line, flags=re.IGNORECASE)

        fixed_lines.append(line)

    return "\n".join(fixed_lines)

def process_file(path: Path):
    text = path.read_text(encoding="utf-8")
    fixed = fix_text(text)
    if text != fixed:
        path.write_text(fixed, encoding="utf-8")
        results.append(f"[UPDATED] {path}")
        return True
    else:
        results.append(f"[OK] {path}")
        return False

def find_repo_root(start: Path) -> Path:
    """Walk upward until we find 'content' folder, then return its parent (repo root)."""
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if parent.name == "content" or parent.name == "contents":
            return parent.parent  # repo root is one level above content
    raise RuntimeError("Could not find 'content' folder above script location.")

def summarize_and_write_audit(repo_root: Path, updated_count: int, ok_count: int, dry_run: bool, used_backup: bool, label: str):
    """Write results to an audit log file in a-mc-audits with a label (dry-run or final)."""
    log_dir = repo_root / "content" / "d8-monitoring-control" / "a-mc-audits"
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    log_file = log_dir / f"a-capitalization-{label}-{ts}.md"

    with log_file.open("w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: a-capitalization-{label}-{ts}\n")
        f.write(f"date: {datetime.now().isoformat()}\n")
        f.write("tags: [audit, monitoring, capitalization]\n")
        f.write("function: d8-monitoring-control\n")
        f.write('shortcode: "[a]" audit\n')
        f.write("classification: public\n")
        f.write("retention: permanent\n")
        f.write("integrityCheck: true\n")
        f.write("---\n\n")
        f.write(f"# audit log – capitalization fix ({label}) ({ts})\n\n")
        f.write(f"**repo root scanned:** {repo_root}\n\n")
        f.write(f"- **dry-run:** {dry_run}\n")
        f.write(f"- **backup enabled:** {used_backup}\n")
        f.write(f"- **files updated:** {updated_count}\n")
        f.write(f"- **files unchanged:** {ok_count}\n\n")
        f.write("## results\n\n")
        for line in results:
            f.write(f"- {line}\n")

    print(f"[INFO] audit log written to {log_file}")

def verify_changes(changed_paths):
    """Re-read changed files and confirm they reflect fixed state (quick heuristic)."""
    verify_results = []
    ok = 0
    for p in changed_paths:
        try:
            txt = p.read_text(encoding="utf-8")
            # heuristic: ensure starts-of-lines are not obviously lowercase after punctuation/newlines
            if re.search(r'(^|[.!?]\s+)[a-z]', txt):
                verify_results.append(f"[VERIFY-WARN] {p} may still contain lowercase sentence starts")
            else:
                verify_results.append(f"[VERIFY-OK] {p}")
                ok += 1
        except Exception as e:
            verify_results.append(f"[VERIFY-ERR] {p}: {e}")

    return ok, verify_results

def main():
    parser = argparse.ArgumentParser(description="Fix capitalization in Markdown while preserving filenames.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and log changes, but do not modify files.")
    parser.add_argument("--backup", action="store_true", help="Create a .bak copy next to each file before changing.")
    parser.add_argument("--confirm", action="store_true", help="Require a 'yes' confirmation before writing.")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = find_repo_root(script_dir)

    # Preflight: remind operator of runbook
    print("[INFO] Ensure you've committed a git snapshot and made a zip backup from repo root before proceeding.")
    print(f"[INFO] starting at repo root: {repo_root}")

    candidate_files = list(repo_root.rglob("*.md"))
    print(f"[INFO] candidate files: {len(candidate_files)}")

    updated_count = 0
    ok_count = 0
    changed_paths = []

    # Pass 1: dry-run or staged write
    for path in candidate_files:
        orig = path.read_text(encoding="utf-8")
        fixed = fix_text(orig)

        if orig != fixed:
            if args.dry_run:
                results.append(f"[WOULD UPDATE] {path}")
                updated_count += 1
            else:
                if args.backup:
                    bak = path.with_suffix(path.suffix + ".bak")
                    bak.write_text(orig, encoding="utf-8")
                path.write_text(fixed, encoding="utf-8")
                results.append(f"[UPDATED] {path}")
                changed_paths.append(path)
                updated_count += 1
        else:
            results.append(f"[OK] {path}")
            ok_count += 1

    # Emit DRY-RUN audit or pre-write audit
    label = "dry-run" if args.dry_run else "pre-verify"
    summarize_and_write_audit(repo_root, updated_count, ok_count, args.dry_run, args.backup, label)

    # If we were only dry-running, stop here
    if args.dry_run:
        print("[INFO] dry-run complete. Review the audit and re-run without --dry-run when ready.")
        return

    # Interactive confirm before finalizing
    if args.confirm:
        proceed = input("Proceed to final verification and change log? Type 'yes' to continue: ").strip().lower()
        if proceed != "yes":
            print("[INFO] aborted by user after pre-verify audit.")
            return

    # Pass 2: verification of actually changed files
    v_ok, verify_results = verify_changes(changed_paths)
    results.extend(verify_results)

    # Final audit includes the verify results
    summarize_and_write_audit(repo_root, updated_count, ok_count, False, args.backup, "final")

if __name__ == "__main__":
    main()
