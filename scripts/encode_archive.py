#!/usr/bin/env python3
"""
Consolidate a period's worth of harvested cloud maps into a compact archive:

  * one near-lossless 8K video per map type  -> the master archive
  * a zip of 2048x1024 (2K) still frames per map type -> lightweight working copies
  * a manifest.csv mapping every video frame to its original timestamp

Video codecs exploit the fact that consecutive cloud maps are nearly identical
(the Earth doesn't move; clouds drift slowly), so the per-map video is a small
fraction of the size of the same frames stored individually -- while staying
visually near-lossless at full 8192x4096.

Usage:
    python scripts/encode_archive.py <input_dir> <output_dir> <week_label>

<input_dir>   flat folder of downloaded assets, e.g. earth_day_20260311_1200.jpg
<output_dir>  created if missing; receives the videos, zips and manifest
<week_label>  e.g. 2026-W26, embedded in the output filenames
"""
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image

# Order matters: clouds_alpha must be tested before clouds (prefix clash).
MAP_TYPES = ["earth_day", "clouds_alpha", "clouds", "earth_night", "specular"]

TWO_K = (2048, 1024)  # 2:1, matches the 8192x4096 source aspect ratio
FRAMERATE = "12"      # playback fps for the timelapse; arbitrary

TS_RE = re.compile(r"(\d{8}_\d{4})")  # the YYYYMMDD_HHMM stamp in each filename


def map_type_of(filename):
    for mt in MAP_TYPES:
        if filename.startswith(mt + "_"):
            return mt
    return None


def timestamp_of(filename):
    m = TS_RE.search(filename)
    return m.group(1) if m else filename


def _hevc(pattern, out_path, crf, vf=None, pix_fmt="yuv444p"):
    """Encode an image sequence to near-lossless HEVC in an mp4."""
    cmd = ["ffmpeg", "-y", "-framerate", FRAMERATE, "-i", pattern]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-c:v", "libx265",
        "-preset", os.environ.get("X265_PRESET", "slow"), "-crf", str(crf),
        "-pix_fmt", pix_fmt, "-tag:v", "hvc1", out_path,
    ]
    print("  $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def group_frames(input_dir):
    """Bucket every file in input_dir by map type, sorted chronologically."""
    groups = {mt: [] for mt in MAP_TYPES}
    for fn in sorted(os.listdir(input_dir)):
        if not os.path.isfile(os.path.join(input_dir, fn)):
            continue
        mt = map_type_of(fn)
        if mt:
            groups[mt].append(fn)
    for mt in groups:
        groups[mt].sort(key=timestamp_of)
    return groups


def encode_video(frames, input_dir, map_type, out_dir, base):
    """Copy frames to a temp sequence and ffmpeg-encode to out_dir.

    Most maps -> one near-lossless 4:4:4 HEVC mp4 (`<base>.mp4`). CRF 20, not
    lower: the source frames are already lossy JPEGs, so preserving them below
    ~20 mostly re-stores JPEG artifacts for little visible gain at double the
    size.

    clouds_alpha is special: it has no reliable lossy-with-alpha codec in the
    ffmpeg toolchain (VP9/AV1 alpha is flaky), and each PNG actually carries two
    grayscale planes -- a cloud-colour layer (RGB) and an alpha mask. We store
    each as its own grayscale HEVC stream (`<base>_color.mp4`, `<base>_mask.mp4`)
    and recombine on extraction (see README). Visually near-lossless, far below
    the ~2 GB a mathematically-lossless codec needs.

    Returns the list of output filenames written.
    """
    ext = os.path.splitext(frames[0])[1].lower()
    with tempfile.TemporaryDirectory() as seq:
        for i, fn in enumerate(frames):
            shutil.copy(os.path.join(input_dir, fn),
                        os.path.join(seq, f"{i:05d}{ext}"))
        pattern = os.path.join(seq, f"%05d{ext}")

        if map_type == "clouds_alpha":
            color, mask = f"{base}_color.mp4", f"{base}_mask.mp4"
            _hevc(pattern, os.path.join(out_dir, color),
                  os.environ.get("ALPHA_COLOR_CRF", "20"),
                  vf="format=gray,format=yuv420p", pix_fmt="yuv420p")
            _hevc(pattern, os.path.join(out_dir, mask),
                  os.environ.get("ALPHA_MASK_CRF", "14"),
                  vf="alphaextract,format=yuv420p", pix_fmt="yuv420p")
            return [color, mask]

        out = f"{base}.mp4"
        _hevc(pattern, os.path.join(out_dir, out),
              os.environ.get("X265_CRF", "20"))
        return [out]


def make_2k_zip(frames, input_dir, out_zip):
    """Downscale each frame to 2K and bundle the set into one zip."""
    with tempfile.TemporaryDirectory() as tmp, \
            zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in frames:
            ext = os.path.splitext(fn)[1].lower()
            out_path = os.path.join(tmp, fn)
            with Image.open(os.path.join(input_dir, fn)) as img:
                resized = img.resize(TWO_K, Image.LANCZOS)
                if ext in (".jpg", ".jpeg"):
                    resized.convert("RGB").save(
                        out_path, "JPEG", quality=90, optimize=True)
                else:  # .png -> keep alpha
                    resized.save(out_path, "PNG", optimize=True)
            zf.write(out_path, fn)


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: encode_archive.py <input_dir> <output_dir> <week_label>")
    input_dir, output_dir, week = sys.argv[1:4]
    os.makedirs(output_dir, exist_ok=True)

    groups = group_frames(input_dir)
    manifest_rows = []

    for mt in MAP_TYPES:
        frames = groups[mt]
        if not frames:
            print(f"[skip] {mt}: no frames found")
            continue
        print(f"[{mt}] {len(frames)} frames")

        encode_video(frames, input_dir, mt, output_dir, f"{mt}_8K_{week}")
        make_2k_zip(frames, input_dir,
                    os.path.join(output_dir, f"{mt}_2K_{week}.zip"))

        for i, fn in enumerate(frames):
            manifest_rows.append([mt, i, timestamp_of(fn), fn])

    manifest_path = os.path.join(output_dir, f"manifest_{week}.csv")
    with open(manifest_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["map_type", "frame_index", "timestamp", "original_filename"])
        w.writerows(manifest_rows)

    print(f"Done. Wrote {len(manifest_rows)} frame records to {manifest_path}")


if __name__ == "__main__":
    main()
