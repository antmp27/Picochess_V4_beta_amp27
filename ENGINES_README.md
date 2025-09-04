# Engines Directory

This repository excludes the `engines/` directory binaries to keep the repository size manageable.

## Missing Engine Files

The following directories are excluded from this repository:
- `engines/aarch64/` - ARM64 engine binaries
- `engines/x86_64/` - x86_64 engine binaries  
- `engines/rodent3/` - Rodent 3 engine files
- `engines/rodent4/` - Rodent 4 engine files

## How to Get Engines

To get the engine files:

1. **Use the installation script**: Run `install-picochess.sh` which will download the necessary engines
2. **Manual download**: Visit the [PicoChess Google Group](https://groups.google.com/g/picochess) for engine downloads
3. **Copy from existing installation**: If you have a working PicoChess installation, copy the engines folder

## Engine Structure

Each engine needs:
- Executable binary (e.g., `stockfish`, `lc0`)
- UCI configuration file (e.g., `stockfish.uci`)
- Entry in `engines.ini`

Refer to the main README.md for detailed engine installation instructions.