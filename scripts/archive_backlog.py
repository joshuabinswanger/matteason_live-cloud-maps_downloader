#!/usr/bin/env python3
"""
Consolidate the backlog of per-run harvest releases (maps-YYYYMMDD_HHMM) into one
compact archive release per ISO week, then optionally delete the raw per-run
releases that were folded in.

For each ISO week (oldest first) it:
  1. downloads every per-run release's assets for that week into a temp dir
  2. runs encode_archive.py -> 8K videos + 2K zips + manifest (kept locally too)
  3. publishes a single `archive-<YYYY-Www>` release with those outputs
  4. unless --no-delete: deletes that week's per-run releases (and their tags)

Safety / behaviour:
  * resumable -- weeks that already have an `archive-*` release are skipped
  * the current (in-progress) ISO week is skipped unless --include-current,
    so it's left to the normal forward weekly-archive flow
  * --dry-run prints the plan (weeks, run counts) and does nothing else
  * delete only happens after the archive release is successfully created
  * local archive copies are written under --archive-dir (syncs to your NAS)

Requires: gh (authenticated) and ffmpeg on PATH, plus Pillow.

Usage:
    python scripts/archive_backlog.py --dry-run
    python scripts/archive_backlog.py --weeks 1            # do one oldest week
    python scripts/archive_backlog.py --no-delete          # archive, keep raw
    python scripts/archive_backlog.py                      # archive + delete all
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

REPO = "joshuabinswanger/matteason_live-cloud-maps_downloader"
HERE = os.path.dirname(os.path.abspath(__file__))
ENCODER = os.path.join(HERE, "encode_archive.py")


DELETE_FAILURES = []


def run_gh(args, retries=6, fatal=True):
    """Run a gh command with retries -- the GitHub API/CLI flakes intermittently
    (transient 401s, rate hiccups) and a single failure shouldn't abort a long
    batch. Returns stdout on success. On exhaustion: raises if fatal, else logs
    and returns None (used for deletes -- a leftover raw release is harmless and
    gets cleaned on the next pass)."""
    for attempt in range(1, retries + 1):
        r = subprocess.run(["gh", *args], text=True, capture_output=True)
        if r.returncode == 0:
            return r.stdout
        # An empty release (failed harvest that published no assets) is benign:
        # there's nothing to download, so skip it rather than retry/abort.
        if "no assets to download" in (r.stderr or "").lower():
            sys.stderr.write(f"[gh] {' '.join(args[:3])}: empty release, skipping\n")
            return ""
        sys.stderr.write(f"[gh retry {attempt}/{retries}] {' '.join(args[:3])} "
                         f"rc={r.returncode}: {r.stderr.strip()[:200]}\n")
        sys.stderr.flush()
        time.sleep(min(30, 5 * attempt))
    if fatal:
        raise RuntimeError(f"gh failed after {retries} attempts: {' '.join(args)}")
    sys.stderr.write(f"[gh GAVE UP -- will retry next run] {' '.join(args)}\n")
    return None


def week_of_tag(tag):
    """ISO week from the capture timestamp in a maps-YYYYMMDD_HHMM tag.

    We use the tag (capture time), NOT the release createdAt -- the backlog was
    bulk-published, so createdAt does not reflect when each map was captured.
    """
    m = re.search(r"(\d{8})_\d{4}", tag)
    if not m:
        return None
    y, w, _ = datetime.strptime(m.group(1), "%Y%m%d").isocalendar()
    return f"{y}-W{w:02d}"


def list_releases():
    out = run_gh(["release", "list", "--repo", REPO, "--limit", "5000",
                  "--json", "tagName,isDraft"])
    return json.loads(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-delete", action="store_true",
                    help="archive but keep the raw per-run releases")
    ap.add_argument("--weeks", type=int, default=0,
                    help="process at most N weeks this run (0 = all)")
    ap.add_argument("--include-current", action="store_true",
                    help="also archive the in-progress ISO week")
    ap.add_argument("--archive-dir",
                    default=r"D:/SynoDrive/2603_CloudMaps/archive",
                    help="where local archive copies are written")
    ap.add_argument("--staging-dir",
                    default=r"D:/SynoDrive/2603_CloudMaps/_backlog_staging")
    args = ap.parse_args()

    releases = list_releases()
    cur_week = f"{datetime.now(timezone.utc).isocalendar()[0]}-W" \
               f"{datetime.now(timezone.utc).isocalendar()[1]:02d}"

    # group maps-* tags by ISO week; note which weeks are already archived
    by_week = defaultdict(list)
    archived = set()
    for r in releases:
        tag = r["tagName"]
        if tag.startswith("archive-"):
            archived.add(tag[len("archive-"):])
        elif tag.startswith("maps-"):
            wk = week_of_tag(tag)
            if wk:
                by_week[wk].append(tag)

    weeks = sorted(by_week)
    todo, cleanup_only = [], []
    for wk in weeks:
        if wk == cur_week and not args.include_current:
            print(f"[skip] {wk}: {len(by_week[wk])} runs -- current week")
        elif wk in archived:
            # archive exists; the raw per-run releases are now redundant
            cleanup_only.append(wk)
        else:
            todo.append(wk)

    print(f"\n{len(weeks)} weeks total, {len(todo)} to archive "
          f"({sum(len(by_week[w]) for w in todo)} per-run releases)")
    if args.weeks:
        todo = todo[:args.weeks]
        print(f"limited to {len(todo)} week(s) this run")
    for wk in todo:
        print(f"  - archive {wk}: {len(by_week[wk])} runs")
    if cleanup_only and not args.no_delete:
        print(f"already archived -- will delete redundant raw releases for: "
              f"{', '.join(cleanup_only)}")

    if args.dry_run:
        print("\n(dry run -- nothing downloaded, archived, or deleted)")
        return

    # weeks already archived: just remove the now-redundant raw releases
    if not args.no_delete:
        for wk in cleanup_only:
            print(f"\n[{wk}] already archived -- deleting "
                  f"{len(by_week[wk])} redundant raw releases")
            for tag in by_week[wk]:
                if run_gh(["release", "delete", tag, "--repo", REPO,
                           "--yes", "--cleanup-tag"], fatal=False) is None:
                    DELETE_FAILURES.append(tag)

    os.makedirs(args.archive_dir, exist_ok=True)
    for wk in todo:
        tags = by_week[wk]
        staging = os.path.join(args.staging_dir, wk)
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        print(f"\n=== {wk}: {len(tags)} runs ===")

        for tag in tags:
            run_gh(["release", "download", tag, "--repo", REPO,
                    "--dir", staging, "--pattern", "*"])

        # encode this week's frames (encode_archive handles the flat staging dir)
        out_dir = os.path.join(args.archive_dir, wk)
        os.makedirs(out_dir, exist_ok=True)
        subprocess.run([sys.executable, ENCODER, staging, out_dir, wk], check=True)

        outputs = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
                   if os.path.isfile(os.path.join(out_dir, f))]
        print(f"[{wk}] publishing archive-{wk} with {len(outputs)} files")
        run_gh(["release", "create", f"archive-{wk}", *outputs,
                "--repo", REPO, "--title", f"8K Archive {wk}",
                "--notes", f"Near-lossless 8K video + 2K stills for ISO "
                           f"week {wk} ({len(tags)} harvest runs). See "
                           f"manifest_{wk}.csv."])

        if not args.no_delete:
            failed = 0
            for tag in tags:
                if run_gh(["release", "delete", tag, "--repo", REPO,
                           "--yes", "--cleanup-tag"], fatal=False) is None:
                    DELETE_FAILURES.append(tag)
                    failed += 1
            print(f"[{wk}] deleted {len(tags) - failed}/{len(tags)} per-run releases")

        shutil.rmtree(staging, ignore_errors=True)

    if DELETE_FAILURES:
        print(f"\n{len(DELETE_FAILURES)} raw releases could not be deleted "
              f"(archived safely; rerun to clean up):")
        for t in DELETE_FAILURES:
            print(f"  {t}")
    print("\nDone.")


if __name__ == "__main__":
    main()
