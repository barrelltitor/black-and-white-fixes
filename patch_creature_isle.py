"""Reversible, version-checked Creature Isle windowed screenshot fix. MIT license."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

TARGET_EXE = 'CreatureIsle.exe'

PATCHES = {
    'CreatureIsle.exe': {
        'original': 'e00b47137c773608fecfd689607290bc693f1a70adbedafe290a1f439a3ac2ce',
        'patched': 'c7f0dbf2eb5ac69d8037f253eb97a78b281570469791f7bf183c635fdfaf12d1',
        'edits': [(o, b'\xe8', b'\xec') for o in (0x43DB6F, 0x43DED3, 0x43DF69, 0x43DF83, 0x43E314)],
    },
}

# Vanilla CI fan patch 1.24 has the same capture layout, but a different hash.
ALTERNATE_BUILDS = {
    'CreatureIsle.exe': [{
        'original': '1a4627fdaea62e3f9a2ee03323ed0a7c2d8315210d6de8eff612606f5da8e3a7',
        'patched': '1f0629289ee027abf8a15162b838e7b0d693ad9df6c6a7954292c88a6a3d114a',
        'edits': PATCHES['CreatureIsle.exe']['edits'],
    }],
}

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
