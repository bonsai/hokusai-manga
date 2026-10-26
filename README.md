# hokusai-manga

NDL IIIF-based research tools for preparing publicly accessible pages of Katsushika Hokusai's *Hokusai Manga* as a compact LoRA training dataset.

## Download all 15 volumes and create a LoRA ZIP

1. Open [Actions → Download and package Hokusai Manga for LoRA](https://github.com/bonsai/hokusai-manga/actions/workflows/download-one-volume.yml).
2. Select **Run workflow** (no inputs required).
3. Wait for the run to finish. It downloads NDL PIDs `851646`–`851660` (volumes 1–15).
4. Download the `hokusai-manga-lora-dataset` artifact from the run summary.
5. Extract `hokusai_manga_lora_dataset.zip` and upload it to Kaggle as a dataset.

The ZIP contains `images/`, one same-name `.txt` caption per image, `dataset.json` provenance/size metadata, and `README.txt`. Captions use the trigger `hokusai_manga`.

### Image compression

The packaging step converts pages to RGB JPEG, resizes the longest edge to at most 1024 px, and saves at JPEG quality 88. This reduces dataset size for an initial LoRA experiment; it is a lossy conversion, so the original downloaded images and IIIF manifests are retained separately in the workflow run workspace, not committed to Git. The artifact retention period is 14 days, so download it promptly.

The workflow continues after individual page-download failures so it can package the pages that succeeded. If any download failed, the run is marked failed after the ZIP artifact is uploaded; inspect the per-volume `errors.txt` files in the artifact.

## Run locally

Python 3.10+ for downloading; Pillow is needed to prepare the compact dataset:

```bash
python scripts/download_ndl_iiif.py --pid 851659 --output output
python -m pip install Pillow
python scripts/package_lora_dataset.py --input output --output dist --max-side 1024 --quality 88
```

Output ZIP: `dist/hokusai_manga_lora_dataset.zip`.

## Rights and responsible use

The NDL records for the original historical volumes identify these digital materials as internet-accessible; still verify the rights and access conditions on each individual record before training, sharing, or redistributing a derived dataset. This tool does not bypass access controls. Downloads are paced to avoid rapid repeated requests; follow NDL's current API terms and guidance.

## IIIF endpoints

- Manifest: `https://dl.ndl.go.jp/api/iiif/<PID>/manifest.json`
- Image requests are derived from each canvas's IIIF image service in the manifest.
