#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release.py — gera um release completo do OTA do i-System Touch (Vision PRO)
===========================================================================

O que ele faz, na ordem:
  1. Lê a FW_VERSION do dwin_bl2.h (você incrementa manualmente quando libera)
  2. Compila o firmware com o PlatformIO (pule com --skip-build)
  3. Copia o .bin para Manifest/firmware.bin e calcula MD5/tamanho
  4. Olha a pasta DWIN_SET do projeto do display: se algum arquivo mudou
     desde o último release, incrementa a versão do display e espelha os
     arquivos em Manifest/display/
  5. Gera o Manifest/manifest.json completo (URLs do raw.githubusercontent)
  6. Comita e faz push — as máquinas passam a ver o release na hora

Uso:
  python release.py --notes "Nota 1" "Nota 2" "Nota 3"
  python release.py --skip-build            # usa o .bin já compilado
  python release.py --force-display         # força re-release do display
  python release.py --no-push               # comita mas não envia pro GitHub
  python release.py --dry-run               # só mostra, não escreve nada

Detalhes:
  - As máquinas SÓ atualizam se "version" for DIFERENTE da FW_VERSION delas;
    o script recusa versão menor que a publicada (evita downgrade acidental).
  - O display atualiza quando "display.version" muda — por isso o bump
    automático quando qualquer .icl/.bin do DWIN_SET muda de md5.
  - Estado (hashes do display) fica em Manifest/.release_state.json.
  - O firmware fica sempre como firmware.bin (a URL no manifest é fixa).
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

# ── Configuração ────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parent
VISION_ROOT  = Path(r"C:\Users\Matheus\Projetos\Vision PRO")

PIO_PROJECT  = VISION_ROOT / "Vision-PRO"
FW_HEADER    = PIO_PROJECT / "src" / "dwin_bl2.h"
PIO_ENV      = "esp32dev"
BUILT_BIN    = PIO_PROJECT / ".pio" / "build" / PIO_ENV / "firmware.bin"
DWIN_SET_DIR = VISION_ROOT / "Design Tela" / "DWIN_SET"

OUT_BIN      = ROOT / "firmware.bin"
OUT_DISPLAY  = ROOT / "display"
MANIFEST     = ROOT / "manifest.json"
STATE_FILE   = ROOT / ".release_state.json"
LEGACY_STATE = ROOT / "manifest_files.json"   # estado do generate_manifest_files.py

BASE_URL     = "https://raw.githubusercontent.com/ma-theuscruz/i-System-Touch---OTA/main"

# Só entram no release os arquivos .icl/.bin com prefixo numérico (id do DWIN)
DISPLAY_EXTS = (".icl", ".bin")
# ────────────────────────────────────────────────────────────────────────────


def die(msg: str) -> None:
    print(f"\nERRO: {msg}")
    sys.exit(1)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_fw_version() -> str:
    if not FW_HEADER.is_file():
        die(f"header do firmware não encontrado: {FW_HEADER}")
    text = FW_HEADER.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'#define\s+FW_VERSION\s+"([^"]+)"', text)
    if not m:
        die(f"FW_VERSION não encontrada em {FW_HEADER}")
    return m.group(1)


def semver_tuple(v: str) -> tuple:
    v = v.lstrip("vV")
    parts = []
    for p in v.split("."):
        m = re.match(r"\d+", p)
        parts.append(int(m.group(0)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def bump_patch(v: str) -> str:
    a, b, c = semver_tuple(v)
    return f"{a}.{b}.{c + 1}"


def find_pio() -> str:
    pio = shutil.which("pio")
    if pio:
        return pio
    for candidate in (Path.home() / ".platformio" / "penv" / "Scripts" / "pio.exe",
                      Path.home() / ".platformio" / "penv" / "bin" / "pio"):
        if candidate.exists():
            return str(candidate)
    die("PlatformIO (pio) não encontrado — instale ou use --skip-build")


def build_firmware() -> None:
    print(f"→ Compilando firmware (pio run -e {PIO_ENV})...")
    result = subprocess.run([find_pio(), "run", "-e", PIO_ENV], cwd=PIO_PROJECT)
    if result.returncode != 0:
        die("build falhou — corrija e rode de novo")


def scan_display() -> dict:
    """{nome: md5} dos arquivos do display elegíveis (prefixo numérico)."""
    if not DWIN_SET_DIR.is_dir():
        die(f"pasta do display não existe: {DWIN_SET_DIR}")
    files = {}
    for p in sorted(DWIN_SET_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() not in DISPLAY_EXTS:
            continue
        if not re.match(r"^\d+", p.name):
            continue
        files[p.name] = md5_of(p)
    if not files:
        die(f"nenhum .icl/.bin com prefixo numérico em {DWIN_SET_DIR}")
    return files


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def load_display_baseline() -> dict:
    """Hashes do último release. Cai no manifest_files.json legado se preciso."""
    state = load_json(STATE_FILE)
    if state.get("display_hashes"):
        return state["display_hashes"]
    legacy = load_json(LEGACY_STATE).get("files") or []
    return {e["name"]: e["md5"] for e in legacy if e.get("name") and e.get("md5")}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=check)


def publish(commit_msg: str, push: bool) -> None:
    if not (ROOT / ".git").exists():
        print("AVISO: Manifest/ não é um repositório git — nada foi comitado.")
        return

    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        print("→ Git: nada mudou, nenhum commit criado.")
        return

    git("commit", "-m", commit_msg)
    print(f"→ Git: commit criado — {commit_msg}")

    if not push:
        print("→ Git: push pulado (--no-push). Envie com: git push")
        return

    r = git("push", check=False)
    if r.returncode != 0:
        print("AVISO: push falhou — o commit está local. Saída do git:")
        print((r.stderr or r.stdout).strip())
        return
    print("→ Git: push OK — o release está no ar.")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Gera o release do OTA do i-System Touch")
    ap.add_argument("--notes", nargs="*", default=None,
                    help="até 3 notas do release")
    ap.add_argument("--skip-build", action="store_true",
                    help="não roda o pio run (usa o firmware.bin já compilado)")
    ap.add_argument("--force-display", action="store_true",
                    help="força re-release do display mesmo sem mudança")
    ap.add_argument("--no-push", action="store_true",
                    help="comita mas não envia pro GitHub")
    ap.add_argument("--dry-run", action="store_true",
                    help="mostra o que seria feito, sem escrever nada")
    args = ap.parse_args()

    print("=" * 64)
    print("  i-System Touch — release do OTA")
    print("=" * 64)

    # 1. Versão do firmware
    fw_version = parse_fw_version()
    prev_manifest = load_json(MANIFEST)
    prev_version = prev_manifest.get("version", "")
    print(f"FW_VERSION (dwin_bl2.h): {fw_version}")
    print(f"Manifest publicado:      {prev_version or '(nenhum)'}")

    if prev_version and semver_tuple(fw_version) < semver_tuple(prev_version):
        die(f"FW_VERSION {fw_version} é MENOR que o manifest atual "
            f"({prev_version}) — incremente a FW_VERSION no dwin_bl2.h.")
    fw_same = bool(prev_version) and fw_version == prev_version

    # 2. Build
    if args.skip_build:
        print("→ Build pulado (--skip-build)")
    elif args.dry_run:
        print(f"→ [dry-run] rodaria: pio run -e {PIO_ENV}")
    else:
        build_firmware()

    if not BUILT_BIN.exists():
        die(f"firmware compilado não existe: {BUILT_BIN}")

    bin_md5 = md5_of(BUILT_BIN)
    bin_size = BUILT_BIN.stat().st_size
    print(f"Firmware:                {bin_size} bytes")
    print(f"MD5:                     {bin_md5}")

    # 3. Display — mudou algo desde o último release?
    display_now = scan_display()
    display_before = load_display_baseline()
    prev_disp_ver = (prev_manifest.get("display") or {}).get("version") or "0.1.0"

    first_baseline = not display_before
    display_changed = args.force_display or (
        not first_baseline and display_now != display_before)

    if first_baseline and not args.force_display:
        disp_ver = prev_disp_ver
        print(f"Display:                 baseline criada ({len(display_now)} "
              f"arquivos, versão {disp_ver} mantida)")
    elif display_changed:
        disp_ver = bump_patch(prev_disp_ver)
        diff = sorted(
            set(display_now) - set(display_before)
            | {n for n in display_now
               if display_before.get(n) not in (None, display_now[n])}
        )
        print(f"Display:                 MUDOU → versão {prev_disp_ver} → {disp_ver}")
        for n in diff[:10]:
            print(f"                           ~ {n}")
        if len(diff) > 10:
            print(f"                           ... e mais {len(diff) - 10}")
    else:
        disp_ver = prev_disp_ver
        print(f"Display:                 sem mudanças (versão {disp_ver})")

    if fw_same and not (display_changed or first_baseline):
        print("\nAVISO: nem o firmware nem o display mudaram de versão — as")
        print("       máquinas vão responder 'nenhuma atualizacao disponivel'.")
        print("       Incremente a FW_VERSION no dwin_bl2.h se este release é")
        print("       de firmware.")
    elif fw_same:
        print("(release só do display — FW_VERSION mantida)")

    # 4. Notas
    if args.notes is None:
        notes = prev_manifest.get("notes") or []
        print("AVISO: sem --notes — reaproveitando as notas do manifest anterior.")
    else:
        notes = args.notes
    notes = [n[:60] for n in notes][:3]
    while len(notes) < 3:
        notes.append("")

    # 5. Monta o manifest
    display_files = [
        {
            "name": name,
            "id": int(re.match(r"^(\d+)", name).group(1)),
            "url": f"{BASE_URL}/display/{name}",
            "size": (DWIN_SET_DIR / name).stat().st_size,
        }
        for name in sorted(display_now,
                           key=lambda n: int(re.match(r"^(\d+)", n).group(1)))
    ]

    manifest = {
        "system_version": fw_version,   # legado (firmwares antigos usavam)
        "version": fw_version,
        "bin": f"{BASE_URL}/firmware.bin",
        "md5": bin_md5,
        "size_bytes": bin_size,
        "released_at": date.today().isoformat(),
        "notes": notes,
        "display": {
            "version": disp_ver,
            "files": display_files,
        },
    }

    if args.dry_run:
        print("\n[dry-run] manifest.json que seria gerado:")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        print("\n[dry-run] nada foi escrito, nada foi comitado.")
        return

    # 6. Escreve tudo
    OUT_DISPLAY.mkdir(exist_ok=True)

    shutil.copy2(BUILT_BIN, OUT_BIN)

    for name, digest in display_now.items():
        dst = OUT_DISPLAY / name
        if not dst.exists() or md5_of(dst) != digest:
            shutil.copy2(DWIN_SET_DIR / name, dst)
    # Remove do espelho o que não existe mais no DWIN_SET
    for p in OUT_DISPLAY.iterdir():
        if p.is_file() and p.name not in display_now:
            p.unlink()
            print(f"                           - removido do espelho: {p.name}")

    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    STATE_FILE.write_text(json.dumps({
        "display_hashes": display_now,
        "display_version": disp_ver,
        "last_release": {"version": fw_version, "date": manifest["released_at"]},
    }, indent=2) + "\n", encoding="utf-8")

    # 7. Publica
    print("-" * 64)
    print(f"OK  →  {MANIFEST}")
    print(f"       {OUT_BIN}")
    print(f"       {OUT_DISPLAY}  ({len(display_now)} arquivos)")
    print()

    if fw_same and not (display_changed or first_baseline):
        commit_msg = f"republish v{fw_version}"
    elif fw_same:
        commit_msg = f"display {disp_ver}"
    else:
        commit_msg = f"v{fw_version}"
    publish(commit_msg, push=not args.no_push)

    print()
    print("Conferir depois:")
    print(f"  curl -s {BASE_URL}/manifest.json")


if __name__ == "__main__":
    main()
