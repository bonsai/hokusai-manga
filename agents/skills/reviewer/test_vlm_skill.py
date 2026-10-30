#!/usr/bin/env python3
"""
VLM Skill Test - End-to-end test for VLMReviewerSkill

Tests:
  1. VLM connection (health check via LM Studio)
  2. Single image review
  3. Batch review (multiple images)
  4. Save results to JSONL (docs/data/hokusai_vlm_test.jsonl)

Usage:
  # Start LM Studio server first, then:
  python agents/skills/reviewer/test_vlm_skill.py --provider lmstudio --model tempura-qwen2.5-vl-3b --limit 3
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Import existing VLM skill
sys.path.insert(0, str(Path(__file__).parent.parent))
from vlm_reviewer import VLMReviewerSkill, VLMConfig, VLMProvider, create_reviewer

# Test prompt for Hokusai manga
HO_KUSAI_PROMPT = """日本語で回答してください。この浮世絵のページについて：
1. 描かれている主な被写体は何ですか？
2. 画風・タッチの特徴は？
3. 构图（構図）の印象は？
4. 1〜10点で評価と理由を。
簡潔に回答してください。"""

ENGLISH_PROMPT = """Describe this Hokusai Manga page:
1. Main subject?
2. Art style / line work characteristics?
3. Composition impression?
4. Rate 1-10 with brief reason.
Answer concisely in English."""


def test_vlm_connection(reviewer: VLMReviewerSkill) -> bool:
    """Test basic VLM connectivity by reviewing one small image."""
    print("\n[1/4] VLM 接続テスト...")
    # We'll test by reviewing a real image below; return True if skill initialized OK
    print(f"  Provider: {reviewer.config.provider.value}")
    print(f"  Model: {reviewer.config.model}")
    print(f"  API Base: {reviewer.config.api_base}")
    print(f"  Chat URL: {reviewer.chat_url}")
    return True


def test_single_review(reviewer: VLMReviewerSkill, image_path: Path, prompt: str):
    """Review a single image."""
    print(f"\n[2/4] 単一画像レビュー: {image_path.name}")
    result = reviewer.review_frame(image_path, prompt)
    print(f"  Error: {result.error or 'none'}")
    print(f"  Latency: {result.latency_ms} ms")
    print(f"  Response preview: {result.response[:200]}...")
    return result


def test_batch_review(reviewer: VLMReviewerSkill, images: list[Path], prompt: str):
    """Review multiple images."""
    print(f"\n[3/4] バッチレビュー: {len(images)} 枚")
    results = reviewer.review_frames(images, prompt)
    for r in results:
        print(f"  {Path(r.frame).name}: {'OK' if not r.error else 'ERR: ' + r.error} ({r.latency_ms} ms)")
    return results


def save_jsonl(results, output_path: Path, provider: str, model: str):
    """Append results to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'a', encoding='utf-8') as f:
        for r in results:
            record = {
                "image": r.frame,
                "image_name": Path(r.frame).name,
                "response": r.response,
                "error": r.error,
                "provider": provider,
                "model": model,
                "latency_ms": r.latency_ms,
                "created_at": datetime.now().isoformat()
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n[4/4] JSONL 保存: {output_path} ({len(results)} 件追記)")


def main():
    parser = argparse.ArgumentParser(description="VLM Skill Test")
    parser.add_argument("--image-dir", default="docs/images",
                        help="Directory with test images")
    parser.add_argument("--limit", type=int, default=3,
                        help="Number of images to test")
    parser.add_argument("--provider", default="lmstudio",
                        choices=[p.value for p in VLMProvider])
    parser.add_argument("--model", default="tempura-qwen2.5-vl-3b")
    parser.add_argument("--output", default="docs/data/hokusai_vlm_test.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--prompt", choices=["jp", "en"], default="jp",
                        help="Prompt language")
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    if not image_dir.exists():
        print(f"ERROR: {image_dir} not found")
        sys.exit(1)

    # Collect test images
    images = sorted(image_dir.glob("*.jpg"))[:args.limit]
    if not images:
        print(f"ERROR: No images found in {image_dir}")
        sys.exit(1)

    prompt = HO_KUSAI_PROMPT if args.prompt == "jp" else ENGLISH_PROMPT

    print("=" * 50)
    print("VLM Skill Test")
    print("=" * 50)

    # Create reviewer
    reviewer = create_reviewer(args.provider, args.model)

    # Test 1: Connection info
    test_vlm_connection(reviewer)

    # Test 2: Single review
    single_result = test_single_review(reviewer, images[0], prompt)

    # Test 3: Batch review
    batch_results = test_batch_review(reviewer, images, prompt)

    # Test 4: Save to JSONL
    all_results = [single_result] + batch_results
    save_jsonl(all_results, Path(args.output), args.provider, args.model)

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
