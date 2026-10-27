#!/usr/bin/env python3
"""
Process exactly 10 resized images per run, save to JSONL + SQLite.
"""
import sys, json, sqlite3, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
IMAGE_DIR = DATA_DIR / "images-hokusai-resized-720"
JSONL_PATH = DATA_DIR / "hokusai_vlm_reviews.jsonl"
DB_PATH = DATA_DIR / "hokusai_vlm_reviews.db"

sys.path.insert(0, str(SCRIPT_DIR))
from vlm_reviewer import create_reviewer, VLMFrame

PROMPT = """Analyze this Hokusai manga illustration. Return ONLY a JSON object:
{"subject":"...","category":"landscape|figure|yokai|daily_life|nature|calligraphy|action|narrative|animals","lora_quality":{"linework":1-10,"contrast":1-10,"composition":1-10,"artifact_free":1-10},"training_suitability":1-10,"notes":"..."}"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, image TEXT UNIQUE, response TEXT, error TEXT, provider TEXT DEFAULT 'lmstudio', model TEXT DEFAULT 'tempura-qwen2.5-vl-3b', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit(); conn.close()

def load_done():
    if not JSONL_PATH.exists(): return set()
    done = set()
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
            if "image" in data: done.add(data["image"])
        except: pass
    return done

def process_batch(limit=10):
    init_db()
    done = load_done()
    all_images = sorted(IMAGE_DIR.glob("*.jpg"))[len(done):len(done)+limit]
    if not all_images:
        print("No remaining images in batch!")
        return
    
    reviewer = create_reviewer("lmstudio", "tempura-qwen2.5-vl-3b")
    
    for img in all_images:
        frame = VLMFrame(path=img)
        print(f"Reviewing {img.name} ...", end="", flush=True)
        try:
            result = reviewer.review_frame(frame, PROMPT)
            if result.error:
                entry = {"image": img.name, "error": result.error}
                print(f" ERROR: {result.error}")
            else:
                entry = {"image": img.name, "response": result.response}
                print(" OK")
        except Exception as e:
            entry = {"image": img.name, "error": str(e)}
            print(f" EXCEPTION: {e}")
        
        with open(JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO reviews (image, response, error) VALUES (?, ?, ?)",
                    (entry["image"], entry.get("response"), entry.get("error")))
        conn.commit(); conn.close()
    
    print(f"Batch complete. Added: {len(all_images)}")

if __name__ == "__main__":
    process_batch(10)
