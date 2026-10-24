"""Adds/removes folders on the *user* PATH (HKCU\\Environment, no admin needed), like Python's "Add to PATH"."""
import ctypes
import os
import sys

if sys.platform == "win32":
    import winreg


def _norm(p):
    return os.path.normcase(os.path.normpath(os.path.expandvars(str(p)).strip().strip('"')))


def _read():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as k:
        try:
            value, kind = winreg.QueryValueEx(k, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
    return value, kind


def _write(value, kind):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Path", 0, kind if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ)
                          else winreg.REG_EXPAND_SZ, value)
    _broadcast()


def _broadcast():
    """Tells Explorer the environment changed, so new command windows see the new PATH."""
    try:
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 3000,
                                                 ctypes.byref(result))
    except Exception:
        pass


def entries():
    value, _ = _read()
    return [e for e in value.split(";") if e.strip()]


def contains(folder):
    target = _norm(folder)
    return any(_norm(e) == target for e in entries())


def add(folders):
    """Appends folders that are not on the user PATH yet (at the end, so existing tools keep priority)."""
    value, kind = _read()
    current = [e for e in value.split(";") if e.strip()]
    have = {_norm(e) for e in current}
    added = [str(f) for f in folders if _norm(f) not in have]
    if added:
        _write(";".join(current + added), kind)
    return added


def remove(folders):
    value, kind = _read()
    drop = {_norm(f) for f in folders}
    current = [e for e in value.split(";") if e.strip()]
    kept = [e for e in current if _norm(e) not in drop]
    if len(kept) != len(current):
        _write(";".join(kept), kind)
    return len(current) - len(kept)
