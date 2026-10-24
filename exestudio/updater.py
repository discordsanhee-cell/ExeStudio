"""Self-update: check a release source, download the new app package, swap files and restart.

Update source (settings["update_source"] or assets/update_source.txt baked in at build time):
  * "owner/repo" or "https://github.com/owner/repo"  -> latest GitHub release (works on any PC)
  * "https://…/manifest.json"                        -> any web host
  * a folder or manifest.json path                    -> local / shared drive
A release carries manifest.json: {"version", "date", "notes", "package", "size", "sha256"} and the package zip
(the app folder without runtime/, which never changes between versions).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from .config import APP_VERSION, DATA_DIR, FROZEN, install_dir, resource_dir

UA = {"User-Agent": "ExeStudio-Updater", "Accept": "application/vnd.github+json"}
STAGING = DATA_DIR / "update_staging"


def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)


def is_newer(remote, local=APP_VERSION):
    return parse_version(remote) > parse_version(local)


def default_source():
    try:
        return (resource_dir() / "assets" / "update_source.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _github_repo(source):
    """'owner/repo' or a github.com URL -> (owner, repo); anything else -> None."""
    s = source.strip().rstrip("/")
    m = re.match(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", s)
    if m:
        return m.group(1), m.group(2)
    m = re.fullmatch(r"([\w.-]+)/([\w.-]+)", s)
    if m and not Path(s).exists():
        return m.group(1), m.group(2)
    return None


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_manifest(source):
    """Returns the manifest dict with an absolute 'package_url' (http URL or local path)."""
    if not source:
        raise RuntimeError("업데이트 주소가 설정되지 않았어요 (설정 → 업데이트).")
    repo = _github_repo(source)
    if repo:
        rel = json.loads(_get(f"https://api.github.com/repos/{repo[0]}/{repo[1]}/releases/latest"))
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        if "manifest.json" in assets:
            man = json.loads(_get(assets["manifest.json"]))
        else:
            man = {"version": rel.get("tag_name", "0").lstrip("vV"), "notes": rel.get("body") or ""}
            man["package"] = next((n for n in assets if n.lower().endswith(".zip")), "")
        man.setdefault("notes", rel.get("body") or "")
        man["package_url"] = assets.get(man.get("package", ""), "")
        man["page"] = rel.get("html_url", "")
        return man
    if source.startswith(("http://", "https://")):
        man = json.loads(_get(source))
        base = source.rsplit("/", 1)[0]
        pkg = man.get("package", "")
        man["package_url"] = pkg if pkg.startswith("http") else f"{base}/{pkg}"
        return man
    p = Path(source)
    if p.is_dir():
        p = p / "manifest.json"
    man = json.loads(p.read_text(encoding="utf-8-sig"))
    man["package_url"] = str(p.parent / man.get("package", ""))
    return man


def check(source):
    """(manifest, newer?)"""
    man = fetch_manifest(source)
    return man, is_newer(man.get("version", "0"))


def download(man, progress=None):
    url = man.get("package_url")
    if not url:
        raise RuntimeError("업데이트 파일 주소가 없어요.")
    STAGING.mkdir(parents=True, exist_ok=True)
    dest = STAGING / f"ExeStudio-{man.get('version', 'new')}.zip"
    if url.startswith(("http://", "https://")):
        req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or man.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 17)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress((done, total))
    else:
        shutil.copyfile(url, dest)
        if progress:
            progress((1, 1))
    want = man.get("sha256")
    if want:
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest().lower() != want.lower():
            dest.unlink(missing_ok=True)
            raise RuntimeError("다운로드한 파일이 손상됐어요 (체크섬 불일치). 다시 시도해 주세요.")
    return dest


def prepare(zip_path):
    """Extracts the package; returns the folder holding ExeStudio.exe."""
    out = STAGING / "files"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    for exe in out.rglob("ExeStudio.exe"):
        return exe.parent
    raise RuntimeError("업데이트 파일 안에 ExeStudio.exe가 없어요.")


def launch_swap(new_dir, target=None, pid=None, restart=True):
    """Starts a hidden script that waits for this process to exit, copies the new files over the install
    folder (runtime/ is kept) and restarts the app. The caller must quit right after."""
    target = Path(target or install_dir())
    pid = pid or os.getpid()
    script = STAGING / "apply_update.ps1"
    log = STAGING / "apply_update.log"

    def q(p):  # PowerShell single-quoted literal
        return "'" + str(p).replace("'", "''") + "'"

    lines = [
        f"$log = {q(log)}",
        f"'waiting for {pid}' | Out-File $log -Encoding utf8",
        f"Wait-Process -Id {pid} -Timeout 300 -ErrorAction SilentlyContinue",
        "Start-Sleep -Milliseconds 500",
        f"robocopy {q(new_dir)} {q(target)} /E /R:10 /W:1 /NP /NFL /NDL /XD runtime | Out-File $log -Append -Encoding utf8",
        "$code = $LASTEXITCODE",
        "\"robocopy exit $code\" | Out-File $log -Append -Encoding utf8",
        "if ($code -ge 8) { exit 1 }",
        f"Remove-Item {q(STAGING / 'files')} -Recurse -Force -ErrorAction SilentlyContinue",
    ]
    if restart:
        lines.append(f"Start-Process -FilePath {q(target / 'ExeStudio.exe')} -WorkingDirectory {q(target)}")
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig", newline="")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("EXESTUDIO_", "_MEI", "_PYI")) and k not in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH")}
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-WindowStyle", "Hidden", "-File", str(script)],
                     creationflags=0x08000000 | 0x00000200,  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
                     close_fds=True, cwd=str(STAGING), env=env)
    return script


def can_self_update():
    return FROZEN and sys.platform == "win32"
