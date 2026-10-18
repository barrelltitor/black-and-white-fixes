"""Reversible, version-checked Black & White windowed screenshot fix. MIT license."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

TARGET_EXE = 'runblack.exe'

PATCHES = {
    'runblack.exe': {
        'original': '3f58bc02a6c421b4e66ef08716646bf0e1fa55ab292786edb521d7596ed48aba',
        'patched': 'b01788bef3fe694124762d01f7261d828625947886b868e007fd2a50e6268d29',
        'edits': [(o, b'\x80', b'\x84') for o in (0x4213AF, 0x421713, 0x4217A9, 0x4217C3, 0x421B54)],
    },
}

ALTERNATE_BUILDS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()

def identify(data, spec):
    checksum = digest(data)
    for state in ('original', 'patched'):
        if checksum == spec[state]:
            return state
    raise ValueError('Unsupported file SHA256: ' + checksum)

def select_spec(data, name):
    checksum = digest(data)
    for spec in [PATCHES[name], *ALTERNATE_BUILDS.get(name, [])]:
        if checksum in (spec['original'], spec['patched']):
            return spec
    raise ValueError('Unsupported file SHA256: ' + checksum)

def transform(data, spec, wanted):
    if identify(data, spec) == wanted:
        return data
    result = bytearray(data)
    for offset, original, patched in spec['edits']:
        old, new = (original, patched) if wanted == 'patched' else (patched, original)
        if result[offset:offset + len(old)] != old:
            raise ValueError('Patch signature mismatch at ' + hex(offset))
        result[offset:offset + len(new)] = new
    result = bytes(result)
    if digest(result) != spec[wanted]:
        raise ValueError('Output checksum does not match the supported target')
    return result

def prepare(folder, names, wanted):
    changes = []
    for name in names:
        path = folder / name
        if path.is_symlink():
            raise ValueError('Refusing to replace a symbolic link: ' + name)
        before = path.read_bytes()
        spec = select_spec(before, name)
        print(name + ': ' + identify(before, spec))
        after = transform(before, spec, wanted) if wanted else before
        if after != before:
            changes.append((path, before, after))
    return changes

def backup_files(folder, changes):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = folder / '.ci-screenshot-fix-backups' / stamp
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for path, before, after in changes:
        copy = destination / path.name
        copy.write_bytes(before)
        if copy.read_bytes() != before:
            raise OSError('Backup verification failed: ' + str(copy))
        manifest[path.name] = {'before': digest(before), 'after': digest(after)}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return destination

def replace_file(path, before, after):
    # Probe without changing bytes; Windows rejects writing mapped game files.
    with path.open('r+b'):
        pass
    if path.read_bytes() != before:
        raise OSError('File changed after validation: ' + str(path))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ci-fix-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != after:
            raise OSError('Temporary file verification failed')
        os.replace(temporary, path)
        if path.read_bytes() != after:
            raise OSError('Installed file verification failed: ' + str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

def run(action, folder):
    names = [TARGET_EXE]
    wanted = {'apply': 'patched', 'restore': 'original', 'status': None}[action]
    changes = prepare(folder, names, wanted)
    if not changes:
        print('No changes needed.')
        return None
    # Validate and back up the executable before replacement.
    backup = backup_files(folder, changes)
    print('Verified backups: ' + str(backup))
    for path, before, after in changes:
        replace_file(path, before, after)
        print('Verified ' + action + ': ' + path.name)
    return backup

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='apply', choices=('status', 'apply', 'restore'))
    args = parser.parse_args()
    try:
        run(args.action, Path(__file__).resolve().parent)
    except (OSError, ValueError) as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
