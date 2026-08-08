"""Download missing official NESO Historic Demand Data source files."""

from __future__ import annotations

from pathlib import Path

import requests

from src.data.neso import NESO_RESOURCES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "neso"


def download_missing_sources(destination: Path = RAW_DIRECTORY) -> list[Path]:
    """Download missing official CSVs atomically without overwriting raw files."""
    destination.mkdir(parents=True, exist_ok=True)
    local_paths: list[Path] = []
    with requests.Session() as session:
        for resource in NESO_RESOURCES.values():
            output = destination / resource["filename"]
            local_paths.append(output)
            if output.exists():
                continue
            temporary = output.with_suffix(output.suffix + ".part")
            try:
                with session.get(resource["url"], stream=True, timeout=120) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as target:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                target.write(chunk)
                temporary.replace(output)
            finally:
                if temporary.exists():
                    temporary.unlink()
    return local_paths


if __name__ == "__main__":
    for source_path in download_missing_sources():
        print(source_path)
