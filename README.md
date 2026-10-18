# Black & White screenshot fixes

Fixes purple save previews in windowed mode. Each patch changes only five bytes
in its game's executable.

## Use

Requires Python 3.9+. Close the game and put the appropriate script beside its
executable, then run:

```powershell
python patch_creature_isle.py    # Beside CreatureIsle.exe
python patch_black_and_white.py  # Beside runblack.exe
```

Run only the script for your game. Append `restore` to undo, or `status` to check.
Backups are verified and saved in `.ci-screenshot-fix-backups`. Unknown executables
are refused. Saves, DLLs, and registry settings are untouched.

Start the game and make a fresh save. Old purple images cannot be recovered.

## Byte changes

The five edits redirect screenshot capture from the primary display surface to
the rendering backbuffer, including matching lock/unlock operations:

- **Creature Isle:** `E8` becomes `EC` in the pointer `0xF0D9E8`, selecting `0xF0D9EC`.
- **Black & White:** `80` becomes `84` in `0xE85080`, selecting `0xE85084`.

These are address bytes inside instructions, not changes to instruction opcodes.
Exact file offsets and supported SHA256 checksums are in each script.

## Compatibility

- **CI Definitive Edition:** verified build tested in-game on Windows 10.
- **Vanilla CI fan patch 1.24:** identical capture code; patch/restore verified.
- **Black & White fan patch 1.42:** equivalent capture code; patch/restore verified.

Vanilla CI and regular Black & White still need in-game confirmation. Other builds,
fullscreen, and creature JPG captures are untested.

Tests: `python -m unittest -v`. MIT licensed; no game files included.

This project was developed with AI assistance.
