#!/usr/bin/env python3
"""
VLM Reviewer Skill for Pi Coding Agent
Provides: vlm_review(frames, prompt), vlm_batch(frames, prompts), vlm_compare(v1, v2)
"""
import os
import sys
import json
import base64
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from skills.base import Skill, Parameter
except ImportError:
    # Fallback for standalone use
    class Skill:
        pass
    class Parameter:
        pass

class VLMProvider(Enum):
    LMSTUDIO = "lmstudio"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CUSTOM = "custom"

@dataclass
class VLMConfig:
    provider: VLMProvider = VLMProvider.LMSTUDIO
    model: str = "tempura-qwen2.5-vl-3b"
    api_base: str = "http://localhost:1234/v1"
    api_key: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.3
    timeout: int = 120

@dataclass
class VLMFrame:
    path: Union[str, Path]
    frame_num: Optional[int] = None
    metadata: Dict[str, Any] = None

@dataclass
class VLMResult:
    frame: str
    frame_num: Optional[int]
    prompt: str
    response: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None

class VLMReviewerSkill(Skill):
    """
    VLM Reviewer Skill - Analyze rendered frames using Vision-Language Models.
    
    Supports multiple providers:
    - LM Studio (local, default)
    - OpenAI GPT-4V
    - Google Gemini
    - Ollama
    - Custom OpenAI-compatible endpoints
    
    Usage:
        skill = VLMReviewerSkill()
        results = skill.review_frames(frames, "Describe lighting and colors")
        results = skill.batch_review(frames, prompts_dict)
        comparison = skill.compare_versions(v1_frames, v2_frames, criteria)
    """
    
    name = "vlm_reviewer"
    description = "Vision-Language Model reviewer for rendered frames"
    version = "1.0.0"
    
    def __init__(self, config: Optional[VLMConfig] = None):
        super().__init__()
        self.config = config or VLMConfig()
        self.session = requests.Session()
        self._setup_provider()
    
    def _setup_provider(self):
        """Configure API endpoints based on provider."""
        if self.config.provider == VLMProvider.LMSTUDIO:
            self.chat_url = f"{self.config.api_base}/chat/completions"
            self.headers = {"Content-Type": "application/json"}
        elif self.config.provider == VLMProvider.OPENAI:
            self.chat_url = "https://api.openai.com/v1/chat/completions"
            self.headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key or os.getenv('OPENAI_API_KEY')}"
            }
        elif self.config.provider == VLMProvider.GEMINI:
            self.chat_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.model}:generateContent"
            self.headers = {"Content-Type": "application/json"}
        elif self.config.provider == VLMProvider.OLLAMA:
            self.chat_url = f"{self.config.api_base}/api/chat"
            self.headers = {"Content-Type": "application/json"}
        else:
            self.chat_url = f"{self.config.api_base}/chat/completions"
            self.headers = {"Content-Type": "application/json"}
    
    def _encode_image(self, image_path: Union[str, Path]) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _build_payload(self, prompt: str, b64_image: str) -> Dict:
        """Build provider-specific payload."""
        if self.config.provider == VLMProvider.LMSTUDIO:
            return {
                "model": self.config.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                    ]
                }],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
        elif self.config.provider == VLMProvider.OPENAI:
            return {
                "model": self.config.model or "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                    ]
                }],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
        elif self.config.provider == VLMProvider.GEMINI:
            return {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_image}}
                    ]
                }],
                "generationConfig": {"maxOutputTokens": self.config.max_tokens, "temperature": self.config.temperature}
            }
        elif self.config.provider == VLMProvider.OLLAMA:
            return {
                "model": self.config.model,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image]
                }],
                "options": {"temperature": self.config.temperature}
            }
        return {}
    
    def _parse_response(self, resp_json: Dict) -> str:
        """Extract text from provider-specific response."""
        if self.config.provider in (VLMProvider.LMSTUDIO, VLMProvider.OPENAI, VLMProvider.OLLAMA):
            return resp_json.get('choices', [{}])[0].get('message', {}).get('content', '')
        elif self.config.provider == VLMProvider.GEMINI:
            return resp_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return str(resp_json)
    
    def review_frame(self, frame: Union[str, Path, VLMFrame], prompt: str) -> VLMResult:
        """Review a single frame with a prompt."""
        import time
        
        if isinstance(frame, VLMFrame):
            frame_path = frame.path
            frame_num = frame.frame_num
        else:
            frame_path = frame
            frame_num = None
        
        frame_path = Path(frame_path)
        if not frame_path.exists():
            return VLMResult(
                frame=str(frame_path), frame_num=frame_num, prompt=prompt,
                response="", provider=self.config.provider.value, model=self.config.model,
                error=f"Frame not found: {frame_path}"
            )
        
        b64 = self._encode_image(frame_path)
        payload = self._build_payload(prompt, b64)
        
        # Add API key for Gemini
        params = {}
        if self.config.provider == VLMProvider.GEMINI:
            params['key'] = self.config.api_key or os.getenv('GEMINI_API_KEY')
        
        start = time.time()
        try:
            resp = self.session.post(
                self.chat_url, json=payload, params=params,
                headers=self.headers, timeout=self.config.timeout
            )
            latency = int((time.time() - start) * 1000)
            
            if resp.status_code == 200:
                response_text = self._parse_response(resp.json())
                return VLMResult(
                    frame=str(frame_path), frame_num=frame_num, prompt=prompt,
                    response=response_text, provider=self.config.provider.value,
                    model=self.config.model, latency_ms=latency
                )
            else:
                return VLMResult(
                    frame=str(frame_path), frame_num=frame_num, prompt=prompt,
                    response="", provider=self.config.provider.value, model=self.config.model,
                    latency_ms=latency, error=f"API {resp.status_code}: {resp.text}"
                )
        except Exception as e:
            return VLMResult(
                frame=str(frame_path), frame_num=frame_num, prompt=prompt,
                response="", provider=self.config.provider.value, model=self.config.model,
                error=str(e)
            )
    
    def review_frames(self, frames: List[Union[str, Path, VLMFrame]], 
                      prompt: str) -> List[VLMResult]:
        """Review multiple frames with same prompt."""
        results = []
        for frame in frames:
            result = self.review_frame(frame, prompt)
            results.append(result)
            if result.error:
                print(f"Error on {frame}: {result.error}")
        return results
    
    def batch_review(self, frames: List[Union[str, Path, VLMFrame]], 
                     prompts: Dict[str, str]) -> Dict[str, List[VLMResult]]:
        """Review frames with different prompts per frame/category."""
        results = {}
        for category, prompt in prompts.items():
            results[category] = self.review_frames(frames, prompt)
        return results
    
    def compare_versions(self, v1_frames: List[Union[str, Path]], 
                         v2_frames: List[Union[str, Path]], 
                         criteria: List[str]) -> Dict[str, Any]:
        """Compare two version frame sets."""
        comparison_prompt = f"""Compare these two MMX spacecraft animation frames (Version 1 vs Version 2).
Evaluate on: {', '.join(criteria)}.
Provide scores (1-10) for each version and a verdict."""
        
        # Use first frame of each version for comparison
        v1_frame = v1_frames[0] if v1_frames else None
        v2_frame = v2_frames[0] if v2_frames else None
        
        if not v1_frame or not v2_frame:
            return {"error": "Need at least one frame per version"}
        
        # This would need multi-image support - simplified for now
        return {
            "v1_frame": str(v1_frame),
            "v2_frame": str(v2_frame),
            "criteria": criteria,
            "note": "Full comparison requires multi-image VLM support"
        }
    
    def save_results(self, results: List[VLMResult], output_path: Path):
        """Save results to JSON."""
        data = [asdict(r) for r in results]
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_frames_from_dir(self, frames_dir: Union[str, Path], 
                             pattern: str = "frame_*.png",
                             max_frames: Optional[int] = None,
                             sample_rate: int = 1) -> List[VLMFrame]:
        """Load frames from directory with optional sampling."""
        frames_dir = Path(frames_dir)
        all_frames = sorted(frames_dir.glob(pattern))
        
        if sample_rate > 1:
            all_frames = all_frames[::sample_rate]
        if max_frames:
            all_frames = all_frames[:max_frames]
        
        vlm_frames = []
        for f in all_frames:
            frame_num = None
            try:
                frame_num = int(f.stem.split('_')[1])
            except:
                pass
            vlm_frames.append(VLMFrame(path=f, frame_num=frame_num))
        return vlm_frames

# Preset prompts for MMX spacecraft review
MMX_REVIEW_PROMPTS = {
    "full": """Analyze this MMX spacecraft animation frame. Provide detailed assessment:
1. Spacecraft visibility - fully visible? any clipping?
2. Color accuracy - can you see white thermal blankets, red/orange propulsion, dark blue solar panels, gray structure?
3. Lighting quality - three-point lighting (sun/fill/rim) working? starfield visible?
4. Camera framing - comfortable distance? rule of thirds? not too close/cluttered?
5. Geometry integrity - any vertex explosions, holes, collapsing meshes?
6. Composition - cinematic? clean? rule of thirds?
7. Overall score (1-10) with justification.""",
    
    "lighting": """Focus on LIGHTING only:
- Sun/key light: direction, intensity, shadows
- Fill light: shadow detail recovery
- Rim light: edge definition, separation from background
- World/background: starfield visibility, not overwhelming
- Overall exposure: over/under exposed?
Score lighting 1-10.""",
    
    "colors": """Focus on COLOR ACCURACY only:
- White thermal blankets (return modules) - visible?
- Red/orange propulsion (tanks) - distinct?
- Dark blue solar panels (paddle) - visible?
- Gray/titanium structure (PAF, legs) - distinct?
- Any color bleeding or washout?
Score color accuracy 1-10.""",
    
    "camera": """Focus on CAMERA FRAMING only:
- Distance: comfortable or claustrophobic?
- Lens: wide enough? distortion?
- Orbit: smooth? dizzying?
- Composition: rule of thirds? centered?
- Clipping: any parts cut off?
Score camera 1-10.""",
    
    "geometry": """Focus on GEOMETRY INTEGRITY only:
- Vertex explosions or spikes?
- Holes or missing faces?
- Decimation artifacts?
- Clean silhouettes?
- Mesh collapsing during animation?
Score geometry 1-10.""",
    
    "quick": """Quick assessment (2-3 sentences):
- What do you see?
- Major issues?
- Score 1-10."""
}

def create_reviewer(provider: str = "lmstudio", model: str = None, **kwargs) -> VLMReviewerSkill:
    """Factory function to create configured reviewer."""
    provider_enum = VLMProvider(provider.lower())
    config = VLMConfig(provider=provider_enum, **kwargs)
    if model:
        config.model = model
    return VLMReviewerSkill(config)

# CLI for standalone use
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="VLM Reviewer Skill CLI")
    parser.add_argument("frames_dir", help="Directory with frame PNGs")
    parser.add_argument("--prompt", choices=list(MMX_REVIEW_PROMPTS.keys()) + ["custom"], default="full")
    parser.add_argument("--custom-prompt", help="Custom prompt text")
    parser.add_argument("--provider", default="lmstudio", choices=[p.value for p in VLMProvider])
    parser.add_argument("--model", default="tempura-qwen2.5-vl-3b")
    parser.add_argument("--sample", type=int, default=4, help="Number of frames to sample")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    frames_dir = Path(args.frames_dir)
    if not frames_dir.exists():
        print(f"Error: {frames_dir} not found")
        sys.exit(1)
    
    # Load frames
    reviewer = create_reviewer(args.provider, args.model)
    frames = reviewer.load_frames_from_dir(frames_dir, sample_rate=max(1, len(list(frames_dir.glob("frame_*.png"))) // args.sample))
    frames = frames[:args.sample]
    
    print(f"Reviewing {len(frames)} frames with {args.provider}/{args.model}...")
    
    prompt = MMX_REVIEW_PROMPTS.get(args.prompt, args.custom_prompt or args.prompt)
    results = reviewer.review_frames(frames, prompt)
    
    for r in results:
        print(f"\n--- Frame {r.frame_num or r.frame} ---")
        if r.error:
            print(f"ERROR: {r.error}")
        else:
            print(r.response[:500] + ("..." if len(r.response) > 500 else ""))
    
    if args.output:
        reviewer.save_results(results, Path(args.output))
        print(f"\nSaved to {args.output}")