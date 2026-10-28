#!/usr/bin/env python3
"""
Hokusai Manga Dataset Reviewer Skill
Batch VLM review of Hokusai manga images for LoRA training dataset curation.
Outputs JSONL + SQLite for dataset analysis.
"""
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Optional

# Import from sibling worker
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vlm_reviewer import create_reviewer, VLMFrame

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "docs" / "data"
DEFAULT_IMAGE_DIR = REPO_ROOT / "docs" / "images"

DEFAULT_PROMPT = """Analyze this Hokusai manga illustration for LoRA training dataset. Return JSON:
{
  "subject": "brief description of what is depicted",
  "category": "landscape|figure|yokai|daily_life|nature|calligraphy|action|narrative|animals",
  "style_notes": "linework quality, composition, period indicators",
  "lora_quality": {"linework": 1-10, "contrast": 1-10, "composition": 1-10, "artifact_free": 1-10},
  "training_suitability": 1-10,
  "notes": "any issues for training (artifacts, blur, text boxes, busy composition)"
}"""

class HokusaiReviewer:
    def __init__(self, provider: str = "lmstudio", model: str = "tempura-qwen2.5-vl-3b", **kwargs):
        self.reviewer = create_reviewer(provider, model, **kwargs)
        self.jsonl_path = DATA_DIR / "hokusai_vlm_reviews.jsonl"
        self.db_path = DATA_DIR / "hokusai_vlm_reviews.db"
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image TEXT UNIQUE,
                response TEXT,
                error TEXT,
                provider TEXT,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def _load_done(self) -> set:
        done = set()
        if self.jsonl_path.exists():
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                try:
                    done.add(json.loads(line)["image"])
                except:
                    pass
        return done
    
    def review_dataset(self, 
                       image_dir: Path,
                       provider: str = "lmstudio",
                       model: str = "tempura-qwen2.5-vl-3b",
                       limit: Optional[int] = None,
                       offset: int = 0,
                       prompt: str = None,
                       **kwargs) -> int:
        """Review all JPGs in directory. Returns count processed."""
        self.reviewer = create_reviewer(provider, model, **kwargs)
        prompt = prompt or DEFAULT_PROMPT
        
        all_jpgs = sorted(image_dir.glob("*.jpg"))[offset:]
        if limit:
            all_jpgs = all_jpgs[:limit]
        
        done = self._load_done()
        remaining = [img for img in all_jpgs if img.name not in done]
        print(f"Total: {len(all_jpgs)}, Done: {len(done)}, Remaining: {len(remaining)}")
        if limit:
            print(f"Limited to: {limit}")
        
        count = 0
        for i, img in enumerate(remaining):
            print(f"[{i+1}/{len(remaining)}] {img.name}...")
            frame = VLMFrame(path=img)
            result = self.reviewer.review_frame(frame, prompt)
            
            entry = {"image": img.name}
            if result.error:
                entry["error"] = result.error
            else:
                entry["response"] = result.response
            
            # Append to JSONL
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
            # Insert to SQLite
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO reviews (image, response, error, provider, model)
                VALUES (?, ?, ?, ?, ?)
            """, (img.name, entry.get("response"), entry.get("error"), provider, model))
            conn.commit()
            conn.close()
            
            count += 1
            print(f"  OK {img.name}")
        
        print(f"Processed {count} images")
        return count
    
    def query_db(self, sql: str):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows
    
    def export_jsonl(self, output_path: Path):
        """Export DB to JSONL."""
        rows = self.query_db("SELECT image, response, error FROM reviews")
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        print(f"Exported {len(rows)} records to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Hokusai Manga Dataset Reviewer")
    parser.add_argument("image_dir", type=Path, nargs="?", default=DEFAULT_IMAGE_DIR, help="Directory with JPG images (default: docs/images)")
    parser.add_argument("--provider", default="lmstudio", choices=["lmstudio", "gemini", "openai", "ollama"])
    parser.add_argument("--model", default="tempura-qwen2.5-vl-3b")
    parser.add_argument("--limit", type=int, help="Max images to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N images")
    parser.add_argument("--prompt", help="Custom prompt (default: LoRA analysis)")
    parser.add_argument("--query", help="Run SQL query on DB")
    parser.add_argument("--export", type=Path, help="Export DB to JSONL file")
    args = parser.parse_args()
    
    reviewer = HokusaiReviewer(args.provider, args.model)
    
    if args.query:
        for row in reviewer.query_db(args.query):
            print(dict(row))
        return
    
    if args.export:
        reviewer.export_jsonl(args.export)
        return
    
    count = reviewer.review_dataset(
        args.image_dir,
        provider=args.provider,
        model=args.model,
        limit=args.limit,
        offset=args.offset,
        prompt=args.prompt
    )
    print(f"\nCompleted: {count} images processed")
    print(f"JSONL: {reviewer.jsonl_path}")
    print(f"SQLite: {reviewer.db_path}")


if __name__ == "__main__":
    main()
