#!/usr/bin/env python3
"""
Reverse of encode_archive.py: decode the archive videos back into 8K map frames.

For each map type it finds the archive video(s), extracts every frame, and names
the output files from manifest.csv so the original timestamps/frame numbers are
restored. clouds_alpha is rebuilt into RGBA by alpha-merging its two grayscale
streams (`*_color.mp4` + `*_mask.mp4`).

Note: the archive videos are lossy (HEVC), so extracted frames are visually
near-identical to the originals, not bit-exact. Output defaults to PNG (a
lossless container for the decoded frame); use --format jpg to re-save as JPEG.
clouds_alpha is always PNG (it needs the alpha channel).

Usage:
    python scripts/extract_archive.py <archive_dir> <output_dir>
                                      [--format png|jpg] [--quality 2]
                                      [--maps earth_day,clouds] [--frame N]

<archive_dir>  folder holding the <map>_8K_<label>.mp4 videos + manifest_*.csv
<output_dir>   created if missing; frames written into <output_dir>/<map>/
--maps         comma-separated subset of map types (default: all present)
--frame N      extract only frame index N (default: every frame)
"""
import argparse
import csv
import glob
import os
import shutil
import subprocess
import sys
import tempfile

MAP_TYPES = ["earth_day", "clouds_alpha", "clouds", "earth_night", "specular"]


def load_manifest(archive_dir):
    """Return {map_type: [original_filename, ...]} ordered by frame_index."""
    hits = glob.glob(os.path.join(archive_dir, "manifest_*.csv"))
    if not hits:
        return None
    if len(hits) > 1:
        print(f"[warn] multiple manifests found, using {os.path.basename(hits[0])}")
    names = {mt: [] for mt in MAP_TYPES}
    with open(hits[0], newline="") as f:
        for row in csv.DictReader(f):
            mt = row["map_type"]
            if mt in names:
                names[mt].append((int(row["frame_index"]), row["original_filename"]))
    for mt in names:
        names[mt] = [fn for _, fn in sorted(names[mt])]
    return names


def find_videos(archive_dir, map_type):
    """Return the video path(s) for a map: (color, mask) for clouds_alpha else (video,)."""
    if map_type == "clouds_alpha":
        color = glob.glob(os.path.join(archive_dir, f"{map_type}_8K_*_color.mp4"))
        mask = glob.glob(os.path.join(archive_dir, f"{map_type}_8K_*_mask.mp4"))
        return (color[0], mask[0]) if color and mask else None
    vids = [v for v in glob.glob(os.path.join(archive_dir, f"{map_type}_8K_*.mp4"))
            if not v.endswith(("_color.mp4", "_mask.mp4"))]
    return (vids[0],) if vids else None


def output_name(map_type, index, manifest, ext):
    """Final filename for a frame, from the manifest when available."""
    if manifest and index < len(manifest[map_type]):
        base = os.path.splitext(manifest[map_type][index])[0]
    else:
        base = f"{map_type}_{index:05d}"
    return f"{base}.{ext}"


def extract_map(map_type, videos, out_dir, manifest, fmt, quality, frame):
    out_ext = "png" if map_type == "clouds_alpha" else fmt
    dst_dir = os.path.join(out_dir, map_type)
    os.makedirs(dst_dir, exist_ok=True)

    # select filter limits extraction to one frame index when requested
    sel = f"select=eq(n\\,{frame})," if frame is not None else ""
    save_opts = ["-vframes", "1"] if frame is not None else []
    jpg_q = ["-qscale:v", str(quality)] if out_ext in ("jpg", "jpeg") else []

    with tempfile.TemporaryDirectory() as tmp:
        pattern = os.path.join(tmp, f"%05d.{out_ext}")
        if map_type == "clouds_alpha":
            color, mask = videos
            fc = (f"[0:v]{sel}format=gbrp[c];[1:v]{sel}format=gray[m];"
                  f"[c][m]alphamerge,format=rgba")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", color, "-i", mask,
                   "-filter_complex", fc, *save_opts, "-start_number", "0", pattern]
        else:
            vf = f"{sel}".rstrip(",")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", videos[0]]
            if vf:
                cmd += ["-vf", vf]
            cmd += [*jpg_q, *save_opts, "-start_number", "0", pattern]
        print(f"[{map_type}] $ {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        extracted = sorted(os.listdir(tmp))
        for i, tmp_name in enumerate(extracted):
            idx = frame if frame is not None else i
            dst = os.path.join(dst_dir, output_name(map_type, idx, manifest, out_ext))
            shutil.move(os.path.join(tmp, tmp_name), dst)
        print(f"[{map_type}] wrote {len(extracted)} frame(s) -> {dst_dir}")
        return len(extracted)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--format", choices=["png", "jpg"], default="png")
    ap.add_argument("--quality", type=int, default=2,
                    help="JPEG qscale 2(best)-31(worst); only with --format jpg")
    ap.add_argument("--maps", default="",
                    help="comma-separated subset, e.g. earth_day,clouds")
    ap.add_argument("--frame", type=int, default=None,
                    help="extract only this frame index")
    args = ap.parse_args()

    manifest = load_manifest(args.archive_dir)
    if manifest is None:
        print("[warn] no manifest_*.csv found; using sequential frame names")

    wanted = [m.strip() for m in args.maps.split(",") if m.strip()] or MAP_TYPES
    total = 0
    for mt in wanted:
        if mt not in MAP_TYPES:
            print(f"[skip] unknown map type: {mt}")
            continue
        videos = find_videos(args.archive_dir, mt)
        if not videos:
            print(f"[skip] {mt}: no archive video found")
            continue
        total += extract_map(mt, videos, args.output_dir, manifest,
                             args.format, args.quality, args.frame)

    print(f"Done. Extracted {total} frame(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
