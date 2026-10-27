#!/usr/bin/env python3
"""
Download Hokusai Manga volumes using rolls.yaml for management.

Usage:
    python download_rolls.py                    # Download all pending volumes
    python download_rolls.py --roll 5           # Download roll 5 only
    python download_rolls.py --roll 5 --skip    # Skip if already downloaded
    python download_rolls.py --status pending   # Show pending rolls
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Try to load yaml; fallback to simple parser
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ROOT = Path(__file__).resolve().parent
ROLLS_PATH = ROOT / "rolls.yaml"
ASSETS_DIR = ROOT / "assets"
SCRIPTS_DIR = ROOT / "scripts"


def parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML parser for rolls.yaml structure."""
    rolls = []
    current = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("- roll:"):
                if current:
                    rolls.append(current)
                current = {"roll": stripped.split(":", 1)[1].strip()}
            elif current and ":" in stripped:
                key, val = stripped.split(":", 1)
                current[key.strip()] = val.strip()
        if current:
            rolls.append(current)
    return {"rolls": rolls}


def load_rolls(path: Path = ROLLS_PATH) -> list[dict]:
    if HAS_YAML:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)["rolls"]
    return parse_simple_yaml(path)["rolls"]


def download_volume(pid: str, assets_dir: Path, delay: float = 0.5) -> bool:
    """Download a single volume using download_ndl_iiif.py."""
    vol_dir = assets_dir / pid
    if vol_dir.exists() and any(vol_dir.glob("*.jpg")):
        print(f"  SKIP  PID {pid}: already has images in {vol_dir}")
        return True
    
    print(f"  DL    PID {pid} → {vol_dir}")
    
    script = SCRIPTS_DIR / "download_ndl_iiif.py"
    if not script.exists():
        print(f"  ERROR: Script not found: {script}")
        return False
    
    import subprocess
    result = subprocess.run(
        [sys.executable, str(script), "--pid", pid, "--output", str(assets_dir), "--delay", str(delay)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        print(f"  OK    PID {pid}: downloaded")
        return True
    else:
        print(f"  FAIL  PID {pid}: {result.stderr[:200]}")
        return False


def update_rolls(roll_num: int, pid: str, success: bool, pages_count: int = 0, total_pages: int = 0):
    """Update rolls.yaml with download status."""
    rolls = load_rolls()
    for r in rolls:
        if int(r.get("roll", 0)) == roll_num:
            r["status"] = "done" if success else "error"
            r["pages_downloaded"] = pages_count
            r["pages_total"] = total_pages
            break
    
    if HAS_YAML:
        import yaml
        with open(ROLLS_PATH, "w", encoding="utf-8") as f:
            yaml.dump({"rolls": rolls}, f, default_flow_style=False, allow_unicode=True)
    else:
        # Simple write — rewrite the file
        lines = []
        with open(ROLLS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # Replace status
        content = content.replace(f"status: pending", f"status: done" if success else f"status: error", 1)
        with open(ROLLS_PATH, "w", encoding="utf-8") as f:
            f.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Hokusai Manga volumes")
    parser.add_argument("--roll", type=int, help="Download specific roll number")
    parser.add_argument("--roll-pid", type=str, help="Download by PID directly")
    parser.add_argument("--status", choices=["pending", "done", "all"], default="all", help="Filter by status")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between image requests")
    parser.add_argument("--skip-done", action="store_true", help="Skip already downloaded volumes")
    args = parser.parse_args()
    
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    
    rolls = load_rolls()
    
    # Filter rolls
    if args.roll:
        rolls = [r for r in rolls if int(r.get("roll", 0)) == args.roll]
    elif args.status != "all":
        rolls = [r for r in rolls if r.get("status") == args.status]
    
    if not rolls:
        print("No matching rolls found.")
        return 0
    
    # Show rolls if roll-pid not specified
    if not args.roll_pid:
        print(f"\n{'Roll':>4} | {'PID':>8} | {'Title':<15} | {'Status':>8} | {'Pages':>10}")
        print("-" * 60)
        for r in rolls:
            pages = f"{r.get('pages_downloaded', 0)}/{r.get('pages_total', 0)}"
            print(f"{r.get('roll', '?'):>4} | {r.get('pid', '?'):>8} | {r.get('title', '')[:15]:<15} | {r.get('status', '?'):>8} | {pages:>10}")
        print()
    
    # Download
    total = len(rolls)
    success = 0
    for i, roll in enumerate(rolls, 1):
        pid = roll.get("pid", "")
        roll_num = roll.get("roll", "?")
        
        if args.skip_done and roll.get("status") == "done":
            print(f"[{i}/{total}] SKIP roll {roll_num} (already done)")
            continue
        
        if args.roll_pid:
            pid = args.roll_pid
            roll_num = "?"
        
        print(f"[{i}/{total}] Downloading roll {roll_num} (PID: {pid})...")
        ok = download_volume(pid, ASSETS_DIR, args.delay)
        if ok:
            success += 1
            if str(roll_num) != "?":
                update_rolls(int(roll_num), pid, True)
        else:
            if str(roll_num) != "?":
                update_rolls(int(roll_num), pid, False)
        print()
    
    print(f"Done: {success}/{total} rolls downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())