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

<input_dir>   either a flat folder of assets (e.g. earth_day_20260311_1200.jpg,
              as CI stages from release assets) OR a nested per-map tree like
              the local downloads/<map>/ layout -- both are handled.
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


def map_type_of(path):
    name = os.path.basename(path)
    for mt in MAP_TYPES:
        if name.startswith(mt + "_"):
            return mt
    return None


def timestamp_of(path):
    name = os.path.basename(path)
    m = TS_RE.search(name)
    return m.group(1) if m else name


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
    """Bucket frames by map type (full paths), sorted chronologically.

    Walks input_dir recursively, so both a flat folder (CI stages release
    assets into one dir) and a nested per-map tree (the local downloads/<map>/
    layout) work. Files are grouped by their map-type filename prefix; duplicate
    basenames across subfolders are ignored after the first seen.
    """
    groups = {mt: [] for mt in MAP_TYPES}
    seen = set()
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            if fn in seen:
                continue
            mt = map_type_of(fn)
            if mt:
                seen.add(fn)
                groups[mt].append(os.path.join(root, fn))
    for mt in groups:
        groups[mt].sort(key=timestamp_of)
    return groups


def encode_video(frame_paths, map_type, out_dir, base):
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
    ext = os.path.splitext(frame_paths[0])[1].lower()
    with tempfile.TemporaryDirectory() as seq:
        for i, src in enumerate(frame_paths):
            shutil.copy(src, os.path.join(seq, f"{i:05d}{ext}"))
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


def make_2k_zip(frame_paths, out_zip):
    """Downscale each frame to 2K and bundle the set into one zip."""
    with tempfile.TemporaryDirectory() as tmp, \
            zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in frame_paths:
            fn = os.path.basename(src)
            ext = os.path.splitext(fn)[1].lower()
            out_path = os.path.join(tmp, fn)
            with Image.open(src) as img:
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

        encode_video(frames, mt, output_dir, f"{mt}_8K_{week}")
        make_2k_zip(frames, os.path.join(output_dir, f"{mt}_2K_{week}.zip"))

        for i, p in enumerate(frames):
            manifest_rows.append([mt, i, timestamp_of(p), os.path.basename(p)])

    manifest_path = os.path.join(output_dir, f"manifest_{week}.csv")
    with open(manifest_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["map_type", "frame_index", "timestamp", "original_filename"])
        w.writerows(manifest_rows)

    print(f"Done. Wrote {len(manifest_rows)} frame records to {manifest_path}")


if __name__ == "__main__":
    main()
