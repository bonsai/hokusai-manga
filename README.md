# Hokusai Manga — NDL IIIF / LoRA dataset

A volume-by-volume workflow for collecting page images from the NDL IIIF manifests for Katsushika Hokusai's *Hokusai Manga*, checking the results, and packaging the collected images for LoRA training.

> **Workflow policy:** download and verify one volume at a time. Do not treat a partial download as complete. Combine the volumes only after reviewing the per-volume artifacts.

## Kanban

Update this board as each volume is processed. The volume is **Done** only when its artifact has been inspected and its missing-page status is understood.

### To do

- [ ] **Volume 1 — PID 851646**
- [ ] **Volume 3 — PID 851648**
- [ ] **Volume 4 — PID 851649**
- [ ] **Volume 5 — PID 851650**
- [ ] **Volume 6 — PID 851651**
- [ ] **Volume 7 — PID 851652**
- [ ] **Volume 8 — PID 851653**
- [ ] **Volume 9 — PID 851654**
- [ ] **Volume 10 — PID 851655**
- [ ] **Volume 11 — PID 851656**
- [ ] **Volume 12 — PID 851657**
- [ ] **Volume 13 — PID 851658**
- [ ] **Volume 14 — PID 851659**
- [ ] **Volume 15 — PID 851660**

### Doing

- [ ] **Volume 2 — PID 851647** — run the one-volume download action and inspect its artifact.

### Done

- [ ] No volumes verified yet.

### Final packaging

- [ ] All 15 volume artifacts collected.
- [ ] Review page counts and `errors.txt` for every volume.
- [ ] Retry any recoverable missing pages.
- [ ] Run the combined LoRA packaging workflow using the volume-download run IDs.
- [ ] Verify the final ZIP and `dataset.json` before uploading to Kaggle.

## How to download one volume

1. Open [Actions: Download one Hokusai Manga volume](https://github.com/bonsai/hokusai-manga/actions/workflows/download-one-volume.yml).
2. Choose **Run workflow** and select exactly one PID from the dropdown.
3. Open that run and check its summary for the number of pages available.
4. Download the artifact named `hokusai-manga-volume-<PID>`.
5. Inspect `pages.json` and `errors.txt`. A run with missing pages is partial, not complete.
6. Move the volume's checkbox from **To do** to **Doing** or **Done** above after checking the artifact.

For the second volume, select PID `851647`. Open [the NDL record for volume 2](https://dl.ndl.go.jp/pid/851647) to cross-check the source record.

## Combine volumes into the LoRA dataset

After the individual volume runs are complete, open [Actions: Combine collected volumes for LoRA](https://github.com/bonsai/hokusai-manga/actions/workflows/package-collected-volumes.yml).

1. Select **Run workflow**.
2. Enter the comma-separated numeric run IDs for the volume-download runs in `run_ids`.
3. Download the artifact `hokusai-manga-lora-dataset-combined`.
4. Inspect the ZIP and dataset manifest before using it for training.

The packaging script creates RGB JPEGs with the longest edge limited to 1024 px (JPEG quality 88), plus a same-name `.txt` caption per image. The trigger word is `hokusai_manga`.

## Local use

Python 3.10+ is recommended. Pillow is required for packaging.

```bash
python scripts/download_ndl_iiif.py --pid 851647 --output output --delay 1.5
python -m pip install Pillow
python scripts/package_lora_dataset.py --input output --output dist --max-side 1024 --quality 88
```

The downloader stores each volume under `output/<PID>/`, including `manifest.json`, `pages.json`, and `errors.txt`. Existing image files with recognized image signatures can be reused on a retry.

## Troubleshooting

- **HTTP 403:** NDL may be denying access to a particular image request. This is not necessarily a transient error; check the record and follow NDL's access conditions.
- **Unexpected Content-Type:** image data is checked by its file signature rather than Content-Type alone. HTML/error responses are not saved as images.
- **Partial volume:** use `pages.json` and `errors.txt` to identify failed pages and rerun that PID after addressing the cause.
- **Combine step fails:** confirm each supplied run ID has a `hokusai-manga-volume-<PID>` artifact and that the artifact has not expired.

## Rights and responsible use

Check the rights and access conditions on each NDL record before training, sharing, or redistributing a derived dataset. This workflow does not bypass access controls. Requests are paced to reduce load; follow NDL's current API terms and guidance.

## IIIF endpoint

`https://dl.ndl.go.jp/api/iiif/<PID>/manifest.json`
