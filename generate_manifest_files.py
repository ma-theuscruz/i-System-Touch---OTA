"""
generate_manifest_files.py
==========================
Atualiza o manifest.json diretamente a partir da pasta do display e do firmware.bin:

  - Recria o bloco "display.files" com nome, id, url e tamanho de cada arquivo
  - Incrementa automaticamente "display.version" quando algum arquivo do display
    mudou (detectado por md5), foi adicionado ou removido
  - Atualiza "md5" e "size_bytes" do firmware.bin
  - NAO altera "version" / "system_version" do firmware (ajuste manual)

O manifest_files.json guarda o md5 de cada arquivo do display entre execucoes,
para detectar mudancas. Nao precisa mais copiar nada manualmente.

Uso:
    python generate_manifest_files.py
"""

import os
import re
import json
import hashlib

# ── Configuração ──────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DISPLAY_FOLDER  = os.path.join(BASE_DIR, "display")
GITHUB_BASE_URL = "https://raw.githubusercontent.com/ma-theuscruz/i-System-Touch---OTA/main/display"
MANIFEST_FILE   = os.path.join(BASE_DIR, "manifest.json")
STATE_FILE      = os.path.join(BASE_DIR, "manifest_files.json")
FIRMWARE_FILE   = os.path.join(BASE_DIR, "firmware.bin")
# ─────────────────────────────────────────────────────────────────────────


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_id(filename: str) -> int | None:
    """Extrai o ID numérico do início do nome do arquivo."""
    m = re.match(r'^(\d+)', filename)
    return int(m.group(1)) if m else None


def bump_patch(version: str) -> str:
    """Incrementa o último número da versão: 0.1.3 -> 0.1.4"""
    parts = version.split(".")
    if parts and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    print(f"  AVISO: versão do display '{version}' não é numérica, mantendo")
    return version


def build_files_list(folder: str, base_url: str) -> list[dict]:
    entries = []

    if not os.path.isdir(folder):
        print(f"ERRO: pasta não encontrada: {folder}")
        return entries

    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".icl", ".bin"):
            continue

        fid = detect_id(fname)
        if fid is None:
            print(f"  AVISO: não foi possível detectar ID de '{fname}', pulando")
            continue

        fpath = os.path.join(folder, fname)
        fsize = os.path.getsize(fpath)
        furl  = f"{base_url.rstrip('/')}/{fname}"

        entries.append({
            "name": fname,
            "id":   fid,
            "url":  furl,
            "size": fsize,
            "md5":  md5_of(fpath),
        })
        print(f"  ok  id={fid:<4}  {fname:<28}  {fsize:>10} bytes")

    entries.sort(key=lambda x: x["id"])
    return entries


def load_previous_md5s() -> dict[str, str] | None:
    """Lê os md5 da execução anterior. None = primeira execução (sem md5 salvos)."""
    if not os.path.isfile(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            files = json.load(f).get("files", [])
    except (json.JSONDecodeError, OSError):
        return None
    if not files or "md5" not in files[0]:
        return None
    return {e["name"]: e["md5"] for e in files}


def display_changed(entries: list[dict], previous: dict[str, str] | None,
                    manifest: dict) -> bool:
    current = {e["name"]: e["md5"] for e in entries}

    if previous is not None:
        return current != previous

    # Primeira execução sem md5 salvos: compara nome+tamanho com o manifest atual
    old = {e.get("name"): e.get("size")
           for e in manifest.get("display", {}).get("files", [])}
    new = {e["name"]: e["size"] for e in entries}
    return old != new


def main():
    print(f"Pasta: {DISPLAY_FOLDER}")
    print(f"Base URL: {GITHUB_BASE_URL}")
    print("-" * 60)

    with open(MANIFEST_FILE, encoding="utf-8") as f:
        manifest = json.load(f)

    entries = build_files_list(DISPLAY_FOLDER, GITHUB_BASE_URL)
    if not entries:
        print("Nenhum arquivo encontrado, manifest não alterado.")
        return

    # ── Versão do display ────────────────────────────────────────────────
    display = manifest.setdefault("display", {})
    old_version = display.get("version", "0.1.0")

    if display_changed(entries, load_previous_md5s(), manifest):
        display["version"] = bump_patch(old_version)
        print(f"Display mudou: versão {old_version} -> {display['version']}")
    else:
        print(f"Display sem mudanças: versão mantida em {old_version}")

    # Bloco files do manifest não leva o md5 (mesmo formato de antes)
    display["files"] = [{k: e[k] for k in ("name", "id", "url", "size")}
                        for e in entries]

    # ── Firmware ─────────────────────────────────────────────────────────
    if os.path.isfile(FIRMWARE_FILE):
        manifest["md5"] = md5_of(FIRMWARE_FILE)
        manifest["size_bytes"] = os.path.getsize(FIRMWARE_FILE)
        print(f"Firmware: md5={manifest['md5']}  size={manifest['size_bytes']} bytes")
        print(f"  (version/system_version mantidos em {manifest.get('version')} — ajuste manual)")
    else:
        print(f"AVISO: firmware.bin não encontrado em {FIRMWARE_FILE}, md5/size mantidos")

    # ── Grava ────────────────────────────────────────────────────────────
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"files": entries}, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("-" * 60)
    print(f"{len(entries)} arquivo(s) processado(s)")
    print(f"manifest.json atualizado: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
