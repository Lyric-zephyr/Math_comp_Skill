"""Locate installed tools even when the launcher inherited an old PATH."""

import os
from pathlib import Path
import shutil


def _registry_paths(name):
    if os.name != "nt":
        return []
    import winreg

    paths = []
    for root, key in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, key) as registry:
                value = os.path.expandvars(winreg.QueryValueEx(registry, "Path")[0])
                paths.extend(Path(part.strip('"')) / (name + ".exe") for part in value.split(os.pathsep) if part)
        except OSError:
            pass
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe") as registry:
                paths.append(Path(os.path.expandvars(winreg.QueryValueEx(registry, "")[0].strip('"'))))
        except OSError:
            pass
    return paths


def find_tool(name):
    variable = "MATH_COMP_" + name.upper()
    configured = os.environ.get(variable)
    if configured:
        path = Path(os.path.expandvars(configured.strip('"'))).expanduser()
        found = shutil.which(str(path)) or (str(path.resolve()) if path.is_file() else None)
        if not found:
            raise FileNotFoundError(f"{variable} 指定的工具不存在：{path}。请修正路径后重试。")
        return found
    candidates = []
    if name in ("xelatex", "initexmf", "miktex", "mpm") and os.environ.get("MATH_COMP_TEX_BIN"):
        directory = Path(os.path.expandvars(os.environ["MATH_COMP_TEX_BIN"].strip('"'))).expanduser()
        configured_tool = directory / (name + (".exe" if os.name == "nt" else ""))
        if configured_tool.is_file():
            return str(configured_tool.resolve())
        if name == "xelatex":
            raise FileNotFoundError(f"MATH_COMP_TEX_BIN 目录中没有 xelatex：{directory}。请选择实际的 bin 目录。")
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    if os.name == "nt":
        candidates.extend(_registry_paths(name))
        for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            if not os.environ.get(variable):
                continue
            root = Path(os.environ[variable])
            for suffix in ("Pandoc", "Programs/Pandoc", "MiKTeX/miktex/bin/x64", "MiKTeX/miktex/bin", "Programs/MiKTeX/miktex/bin/x64", "Programs/MiKTeX/miktex/bin"):
                candidates.append(root / suffix / (name + ".exe"))
            for directory in root.glob("MiKTeX*/miktex/bin/*"):
                candidates.append(directory / (name + ".exe"))
        texlive = Path(os.environ.get("SystemDrive", "C:") + "/") / "texlive"
        candidates.extend(texlive.glob(f"*/bin/windows/{name}.exe"))
        candidates.extend(texlive.glob(f"*/bin/win32/{name}.exe"))
    else:
        candidates.extend(Path(directory) / name for directory in ("/Library/TeX/texbin", "/usr/local/bin", "/opt/homebrew/bin"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def tool_environment(*tools):
    env = os.environ.copy()
    directories = list(dict.fromkeys(str(Path(tool).parent) for tool in tools if tool))
    env["PATH"] = os.pathsep.join(directories + [env.get("PATH", "")])
    return env
