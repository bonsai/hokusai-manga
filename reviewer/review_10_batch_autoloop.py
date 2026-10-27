#!/usr/bin/env python3
"""
Loop: process 10 images, wait, repeat until all done.
Resizes not needed (already resized).
"""
import sys, json, sqlite3, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "vlm_reviewer"))
from vlm_reviewer import create_reviewer, VLMFrame

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
IMAGE_DIR = DATA_DIR / "images-hokusai-resized-720"
JSONL_PATH = DATA_DIR / "hokusai_vlm_reviews.jsonl"
DB_PATH = DATA_DIR / "hokusai_vlm_reviews.db"

PROMPT = """Analyze this Hokusai manga illustration. Return ONLY JSON:
{"subject":"...","category":"landscape|figure|yokai|daily_life|nature|calligraphy|action|narrative|animals","lora_quality":{"linework":1-10,"contrast":1-10,"composition":1-10,"artifact_free":1-10},"training_suitability":1-10,"notes":"..."}"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, image TEXT UNIQUE, response TEXT, error TEXT, provider TEXT DEFAULT 'lmstudio', model TEXT DEFAULT 'tempura-qwen2.5-vl-3b', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit(); conn.close()

def load_done():
    if not JSONL_PATH.exists(): return set()
    done = set()
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if "image" in d: done.add(d["image"])
        except: pass
    return done

def main():
    init_db()
    total_done = len(load_done())
    all_imgs = sorted(IMAGE_DIR.glob("*.jpg"))
    print(f"Total images: {len(all_imgs)} | Already done: {total_done}")
    
    batch_num = 1
    while True:
        done = load_done()
        remaining = [img for img in all_imgs if img.name not in done]
        if not remaining:
            print("\nALL IMAGES REVIEWED!")
            break
        
        batch = remaining[:10]
        print(f"\n=== Batch {batch_num}: {len(batch)} images ({len(done)}/{len(all_imgs)} done) ===")
        
        reviewer = create_reviewer("lmstudio", "tempura-qwen2.5-vl-3b")
        success = 0
        
        for img in batch:
            frame = VLMFrame(path=img)
            try:
                result = reviewer.review_frame(frame, PROMPT)
                entry = {"image": img.name}
                if result.error:
                    entry["error"] = result.error
                    print(f"  {img.name}: ERROR")
                else:
                    entry["response"] = result.response
                    success += 1
                    print(f"  {img.name}: OK")
            except Exception as e:
                entry = {"image": img.name, "error": str(e)}
                print(f"  {img.name}: EXCEPTION")
            
            with open(JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO reviews (image, response, error) VALUES (?, ?, ?)",
                        (entry["image"], entry.get("response"), entry.get("error")))
            conn.commit(); conn.close()
        
        print(f"Batch {batch_num}: {success}/{len(batch)} success")
        total_done = len(load_done())
        print(f"Progress: {total_done}/{len(all_imgs)}")
        
        batch_num += 1
        time.sleep(2)

if __name__ == "__main__":
    main()
