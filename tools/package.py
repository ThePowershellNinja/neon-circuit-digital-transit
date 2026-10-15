"""Build a deterministic, directly installable KWin/Effect archive."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "LICENSE": ROOT / "LICENSE",
    "metadata.json": ROOT / "effect/metadata.json",
    "contents/code/main.js": ROOT / "effect/contents/code/main.js",
    "contents/config/main.xml": ROOT / "effect/contents/config/main.xml",
    "contents/shaders/digital.frag": ROOT / "effect/contents/shaders/digital.frag",
}


def validate():
    metadata = json.loads(FILES["metadata.json"].read_text())
    plugin = metadata["KPlugin"]
    assert metadata["KPackageStructure"] == "KWin/Effect"
    assert plugin["Id"] == "neon-digital-minimize"
    assert plugin["License"] == "MIT" and plugin["EnabledByDefault"] is False
    assert plugin["Authors"] == [{"Name": "ThePowershellNinja"}]
    assert plugin["Website"] == "https://github.com/ThePowershellNinja/neon-circuit-digital-transit"
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["Version"]), "Expected an x.y.z version"
    assert metadata["X-Plasma-API"] == "javascript"
    assert metadata["X-Plasma-MainScript"] == "code/main.js"
    assert metadata["X-KWin-Exclusive-Category"] == "minimize"
    config = ET.fromstring(FILES["contents/config/main.xml"].read_text())
    ns = {"k": "http://www.kde.org/standards/kcfg/1.0"}
    assert config.find(".//k:entry[@name='Duration']/k:default", ns).text == "300"
    assert "readConfig(\"Duration\", 300)" in FILES["contents/code/main.js"].read_text()
    license_text = FILES["LICENSE"].read_text()
    assert license_text.startswith("MIT License\n")
    assert "Permission is hereby granted" in license_text
    for path in FILES.values():
        assert path.is_file() and not path.is_symlink(), path
    return plugin["Version"]


def build(output):
    version = validate()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"neon-circuit-digital-transit-{version}.tar.gz"
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
                for name, path in sorted(FILES.items()):
                    content = path.read_bytes()
                    entry = tarfile.TarInfo(name)
                    entry.size = len(content)
                    entry.mode = 0o644
                    tar.addfile(entry, io.BytesIO(content))
    with tarfile.open(archive) as tar:
        assert set(tar.getnames()) == set(FILES)
        for entry in tar.getmembers():
            assert entry.isfile() and entry.name in FILES
            assert tar.extractfile(entry).read() == FILES[entry.name].read_bytes()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(args.output))
