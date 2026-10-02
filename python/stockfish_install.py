"""Download Stockfish on the first run.

App Lab runs the app as a normal user in a container, so `apt install`
can't work. Instead this fetches the Debian stockfish package for this
board's architecture straight from the Debian mirror and unpacks the
engine binary into the app's data folder. Pure Python: no apt, dpkg or root.
"""
import io
import lzma
import os
import platform
import stat
import subprocess
import tarfile
import urllib.request

MIRROR = os.environ.get("STOCKFISH_MIRROR", "http://deb.debian.org/debian")
ARCHES = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}


def _codename():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("VERSION_CODENAME="):
                    return line.split("=", 1)[1].strip().strip('"') or "trixie"
    except OSError:
        pass
    return "trixie"


def _get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def _package_path(codename, arch, components):
    for comp in components:
        index = lzma.decompress(_get(f"{MIRROR}/dists/{codename}/{comp}/binary-{arch}/Packages.xz"))
        for stanza in index.decode("utf-8", "replace").split("\n\n"):
            fields = dict(line.split(": ", 1) for line in stanza.splitlines()
                          if ": " in line and not line.startswith(" "))
            if fields.get("Package") == "stockfish":
                return fields["Filename"]
    raise RuntimeError(f"No stockfish package for {codename}/{arch} on {MIRROR}")


def _decompress_zst(data):
    """Debian packages use xz, which tarfile reads itself; Ubuntu uses zstd."""
    try:
        from compression import zstd                # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        pass
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(data)
    except ImportError:
        return subprocess.run(["zstd", "-dc"], input=data, capture_output=True, check=True).stdout


def _data_tar(deb):
    """Return the data.tar.* member of a .deb (an `ar` archive)."""
    if not deb.startswith(b"!<arch>\n"):
        raise RuntimeError("Not a .deb file")
    pos = 8
    while pos < len(deb):
        header = deb[pos:pos + 60]
        name = header[:16].decode().strip().rstrip("/")
        size = int(header[48:58])
        body = deb[pos + 60:pos + 60 + size]
        if name.startswith("data.tar"):
            return _decompress_zst(body) if name.endswith(".zst") else body
        pos += 60 + size + (size % 2)
    raise RuntimeError("No data.tar in the stockfish package")


def install(dest_dir, codename=None, components=("main",)):
    """Make sure dest_dir/stockfish exists and return its path."""
    path = os.path.join(dest_dir, "stockfish")
    if os.access(path, os.X_OK):
        return path
    arch = ARCHES.get(platform.machine())
    if not arch:
        raise RuntimeError(f"Don't know the Debian name for {platform.machine()}")
    deb = _get(f"{MIRROR}/{_package_path(codename or _codename(), arch, components)}")
    with tarfile.open(fileobj=io.BytesIO(_data_tar(deb))) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("usr/games/stockfish"))
        binary = tar.extractfile(member).read()
    os.makedirs(dest_dir, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(binary)
    os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, path)
    return path


if __name__ == "__main__":
    import sys
    print(install(sys.argv[1] if len(sys.argv) > 1 else "."))
