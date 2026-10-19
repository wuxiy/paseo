#!/usr/bin/env python3
"""Verify a Lazycat LPK v2 package's embedded OCI image is complete and intact.

Reads the tar directly (no extraction): every digest referenced from
images/index.json -> manifests -> configs+layers must exist in
images/blobs/sha256/ and hash to its own filename. Catches the
"archive/tar: invalid tar header" class of failure before it reaches a box.

Usage: python3 verify_lpk.py <package.lpk>
"""

import hashlib
import json
import sys
import tarfile


def read_json(tf, name):
    member = tf.getmember(name)
    return json.loads(tf.extractfile(member).read().decode("utf-8"))


def main(path):
    errors = []
    checked = 0
    total_bytes = 0
    with tarfile.open(path, "r:") as tf:
        names = set(tf.getnames())
        for required in ("images/index.json", "manifest.yml", "package.yml"):
            if required not in names:
                errors.append(f"missing {required}")

        index = read_json(tf, "images/index.json")
        manifests = index.get("manifests", [])
        if not manifests:
            errors.append("images/index.json has no manifests")
        for entry in manifests:
            digest = entry["digest"]
            blob_name = "images/blobs/sha256/" + digest.split(":", 1)[1]
            if blob_name not in names:
                errors.append(f"manifest blob missing: {blob_name}")
                continue
            manifest = read_json(tf, blob_name)
            referenced = [manifest["config"]["digest"]]
            referenced += [layer["digest"] for layer in manifest.get("layers", [])]
            for ref in referenced:
                rel = "images/blobs/sha256/" + ref.split(":", 1)[1]
                if rel not in names:
                    errors.append(f"referenced blob missing: {rel}")
                    continue
                h = hashlib.sha256()
                size = 0
                with tf.extractfile(tf.getmember(rel)) as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                        size += len(chunk)
                actual = "sha256:" + h.hexdigest()
                if actual != ref:
                    errors.append(f"digest mismatch for {rel}: expected {ref}, got {actual}")
                checked += 1
                total_bytes += size

    if errors:
        for err in errors:
            print("ERROR:", err)
        print(f"FAIL: {len(errors)} problem(s), {checked} blobs verified")
        return 1
    print(f"OK: {checked} blobs verified, {total_bytes / 1024 / 1024:.1f} MiB of referenced layers/configs")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
