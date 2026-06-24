"""
generate_manifest_files.py
==========================
Gera o bloco "files" do manifest.json a partir da pasta de arquivos do display.

Uso:
    python generate_manifest_files.py

Saída: manifest_files.json (pronto para copiar no manifest.json)

Configuração:
    - DISPLAY_FOLDER : pasta onde estão os arquivos .icl / .bin
    - GITHUB_BASE_URL: URL raw do GitHub onde os arquivos serão hospedados
"""

import os
import re
import json

# ── Configuração ──────────────────────────────────────────────────────────
DISPLAY_FOLDER  = r"C:\Users\Matheus\Projetos\i-System Touch\Manifest\display"
GITHUB_BASE_URL = "https://raw.githubusercontent.com/ma-theuscruz/i-System-Touch---OTA/main/display"
OUTPUT_FILE     = os.path.join(os.path.dirname(__file__), "manifest_files.json")
# ─────────────────────────────────────────────────────────────────────────


def detect_id(filename: str) -> int | None:
    """Extrai o ID numérico do início do nome do arquivo."""
    m = re.match(r'^(\d+)', filename)
    return int(m.group(1)) if m else None


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
            "size": fsize
        })
        print(f"  ✓  id={fid:<4}  {fname:<28}  {fsize:>10} bytes")

    # Ordena por ID numérico
    entries.sort(key=lambda x: x["id"])
    return entries


def main():
    print(f"Pasta: {DISPLAY_FOLDER}")
    print(f"Base URL: {GITHUB_BASE_URL}")
    print("-" * 60)

    files = build_files_list(DISPLAY_FOLDER, GITHUB_BASE_URL)

    if not files:
        print("Nenhum arquivo encontrado.")
        return

    # Monta o JSON com o bloco completo "files"
    output = {"files": files}
    json_str = json.dumps(output, indent=2, ensure_ascii=False)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json_str)

    print("-" * 60)
    print(f"{len(files)} arquivo(s) processado(s)")
    print(f"Saída: {OUTPUT_FILE}")
    print()
    print("Cole o conteúdo de 'files' abaixo no seu manifest.json:")
    print()

    # Imprime só o array (sem o wrapper) para facilitar o copy-paste
    files_only = json.dumps(files, indent=6, ensure_ascii=False)
    # Ajusta indentação para ficar bonito dentro do manifest
    print('      "files": ' + files_only)


if __name__ == "__main__":
    main()
