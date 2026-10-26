# hokusai-manga

NDL IIIF-based research tools for downloading publicly accessible pages of Katsushika Hokusai's *Hokusai Manga*.

## Download one volume with GitHub Actions

1. Open **Actions → Download one NDL volume**.
2. Select **Run workflow**.
3. Enter an NDL PID (default: `851659`, a candidate volume record).
4. Run the workflow and open the completed run.
5. Download the `hokusai-manga-pid-<PID>` artifact from the run summary.

The workflow downloads page images into a ZIP artifact. It does **not** commit book scans to Git, keeping the repository small. Availability and image access depend on the specific NDL record and its IIIF manifest.

## Run locally

Python 3.10+; no third-party packages required:

```bash
python scripts/download_ndl_iiif.py --pid 851659 --output output
```

Output is written under `output/<PID>/`, including the source manifest and numbered JPEG pages. Use a PID for a record that is accessible online and exposes page images through NDL's IIIF API.

## Rights and responsible use

Check the individual NDL record's access conditions and rights information before reuse or redistribution. This tool does not bypass access controls. Downloads are paced to avoid sending rapid repeated requests; follow NDL's current API terms and guidance.

## IIIF endpoints

- Manifest: `https://www.dl.ndl.go.jp/api/iiif/<PID>/manifest.json`
- Image requests are derived from each canvas's IIIF image service in the manifest.
