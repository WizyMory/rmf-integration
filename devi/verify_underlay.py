#!/usr/bin/env python3
"""Compare audited Devi files with their original SHA-256, without changing them."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='/home/devi/devi_ws/src')
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).parent/'reference/manifest.json').read_text())
    errors = []
    for name, digest in manifest['files'].items():
        path = Path(args.source)/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(name)
    print(json.dumps({'files_checked': len(manifest['files']),
                      'all_original_files_unchanged': not errors,
                      'changed_or_missing': errors}, indent=2))
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
