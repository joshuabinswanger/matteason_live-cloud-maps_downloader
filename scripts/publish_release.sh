#!/usr/bin/env bash
# Publish every file under $DIR (default downloads/) as GitHub release $TAG,
# titled $TITLE. Success means every file is on the release at its full local
# size; anything missing is re-uploaded, so re-running for an existing tag also
# tops up a release a failed run left half-finished (or as a draft).
set -uo pipefail
DIR="${DIR:-downloads}"
ATTEMPTS="${ATTEMPTS:-6}"

mapfile -t FILES < <(find "$DIR" -type f | sort)
if [ "${#FILES[@]}" -eq 0 ]; then
  echo "::error::no files in $DIR to publish"
  exit 1
fi

# Prints the files not yet on the release at their local size. Fails when the
# release can't be read: it doesn't exist yet, or the API hiccuped.
missing_files() {
  local have
  have=$(gh release view "$TAG" --json assets \
           --jq '.assets[] | select(.state == "uploaded") | "\(.name) \(.size)"' 2>/dev/null) || return 1
  for f in "${FILES[@]}"; do
    grep -qxF "$(basename "$f") $(stat -c %s "$f")" <<<"$have" || echo "$f"
  done
}

publish_if_complete() {
  local missing
  missing=$(missing_files) && [ -z "$missing" ] &&
    gh release edit "$TAG" --draft=false >/dev/null &&
    echo "$TAG published with ${#FILES[@]} files"
}

for attempt in $(seq 1 "$ATTEMPTS"); do
  publish_if_complete && exit 0
  if missing=$(missing_files); then
    mapfile -t todo <<<"$missing"
    echo "attempt $attempt: uploading ${#todo[@]} missing file(s)"
    gh release upload "$TAG" "${todo[@]}" --clobber
  else
    echo "attempt $attempt: creating $TAG"
    gh release create "$TAG" "${FILES[@]}" --title "$TITLE" --notes ""
  fi
  sleep $(( attempt * 10 ))
done
publish_if_complete && exit 0

echo "::error::$TAG is still missing files after $ATTEMPTS attempts"
exit 1
