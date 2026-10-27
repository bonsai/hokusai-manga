#!/usr/bin/env python3
"""
Batch process ALL Hokusai images with VLM review.
Runs in background, saves incrementally to JSONL + SQLite.
"""
import sys
import json
import sqlite3
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
IMAGE_DIR = DATA_DIR / "images-hokusai-resized-720"
JSONL_PATH = DATA_DIR / "hokusai_vlm_reviews.jsonl"
DB_PATH = DATA_DIR / "hokusai_vlm_reviews.db"

sys.path.insert(0, str(SCRIPT_DIR))
from vlm_reviewer import create_reviewer, VLMFrame

PROMPT = """Analyze this Hokusai manga illustration for LoRA training dataset. Return JSON:
{
  "subject": "brief description of what is depicted",
  "category": "landscape|figure|yokai|daily_life|nature|calligraphy|action|narrative|animals",
  "style_notes": "linework quality, composition, period indicators",
  "lora_quality": {"linework": 1-10, "contrast": 1-10, "composition": 1-10, "artifact_free": 1-10},
  "training_suitability": 1-10,
  "notes": "any issues for training (artifacts, blur, text boxes, busy composition)"
}"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
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

def load_done():
    done = set()
    if JSONL_PATH.exists():
        for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["image"])
            except:
                pass
    return done

def main():
    print(f"Starting batch review of Hokusai dataset")
    print(f"Image dir: {IMAGE_DIR}")
    print(f"Output: {JSONL_PATH}, {DB_PATH}")
    
    init_db()
    done = load_done()
    all_jpgs = sorted(IMAGE_DIR.glob("*.jpg"))
    remaining = [img for img in all_jpgs if img.name not in done]
    
    print(f"Total images: {len(all_jpgs)}")
    print(f"Already done: {len(done)}")
    print(f"Remaining: {len(remaining)}")
    
    if not remaining:
        print("All images already processed!")
        return
    
    reviewer = create_reviewer("lmstudio", "tempura-qwen2.5-vl-3b")
    
    total_start = time.time()
    success = 0
    errors = 0
    
    for i, img in enumerate(remaining):
        frame = VLMFrame(path=img)
        result = reviewer.review_frame(frame, PROMPT)
        
        entry = {"image": img.name}
        if result.error:
            entry["error"] = result.error
            errors += 1
            print(f"  [{i+1}/{len(remaining)}] {img.name} - ERROR: {result.error}")
        else:
            entry["response"] = result.response
            success += 1
            print(f"  [{i+1}/{len(remaining)}] {img.name} - OK")
        
        # Append to JSONL
        with open(JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        # Insert to SQLite
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO reviews (image, response, error, provider, model)
            VALUES (?, ?, ?, ?, ?)
        """, (img.name, entry.get("response"), entry.get("error"), "lmstudio", "tempura-qwen2.5-vl-3b"))
        conn.commit()
        conn.close()
        
        # Progress every 10
        if (i + 1) % 10 == 0:
            elapsed = time.time() - total_start
            rate = (i + 1) / elapsed
            eta = (len(remaining) - i - 1) / rate if rate > 0 else 0
            print(f"  Progress: {i+1}/{len(remaining)} | Success: {success} | Errors: {errors} | Rate: {rate:.2f}/s | ETA: {eta/60:.1f}min")
    
    total_elapsed = time.time() - total_start
    print(f"\n{'='*50}")
    print(f"BATCH COMPLETE")
    print(f"Total time: {total_elapsed/60:.1f} minutes")
    print(f"Success: {success}, Errors: {errors}")
    print(f"Average rate: {len(remaining)/total_elapsed:.2f} images/sec")

if __name__ == "__main__":
    main()
