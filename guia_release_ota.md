# Guia de Release — Eurowash OTA

---

## Cenário 1 — Atualizar Display + Firmware ESP

> Use quando mudou qualquer arquivo `.icl` / `.bin` do display **e** também gerou um novo `.bin` da ESP.

### Passo a passo

**1. Compile o novo firmware da ESP**

No PlatformIO, rode:
```
pio run --target release
```
O arquivo gerado fica em `.pio/build/<env>/firmware.bin`.

---

**2. Atualize os arquivos do display**

Copie os arquivos `.icl` / `.bin` modificados para:
```
C:\Users\Matheus\Projetos\Eurolatte\Manifest\display\
```

---

**3. Gere o bloco `"files"` do manifest**

Na pasta `C:\Users\Matheus\Projetos\Eurolatte\Manifest\`, rode:
```
python generate_manifest_files.py
```
O script imprime o bloco `"files"` completo com tamanhos reais em bytes.

---

**4. Calcule o MD5 do firmware.bin**

PowerShell:
```powershell
Get-FileHash .pio\build\<env>\firmware.bin -Algorithm MD5
```

---

**5. Atualize o `manifest.json`**

```json
{
  "system_version": "1.0.1",        ← incrementa (gatilho de update)
  "version":        "0.1.5",        ← versão do firmware ESP
  "bin":  "https://raw.githubusercontent.com/ma-theuscruz/WasherUpdate/main/firmware.bin",
  "md5":  "<hash calculado no passo 4>",
  "size_bytes": <tamanho em bytes do firmware.bin>,
  "released_at": "2026-03-22",
  "notes": [
    "Descrição da mudança 1",
    "Descrição da mudança 2",
    "Descrição da mudança 3"
  ],
  "display": {
    "version": "1.0.1",             ← mesmo valor do system_version
    "files": [
      <cole aqui a saída do generate_manifest_files.py>
    ]
  }
}
```

> **Regra:** `system_version`, `version` e `display.version` devem ser todos iguais quando ambos mudam.

---

**6. Suba tudo para o GitHub**

```
WasherUpdate/
├── manifest.json          ← atualizado
├── firmware.bin           ← novo .bin da ESP
└── display/
    ├── 32.icl             ← arquivos modificados
    └── ...
```

Commit e push na branch `main`.

---

**7. Verifique no Serial Monitor**

Na próxima inicialização da máquina, você verá:
```
=== OTA: verificando manifest ===
Manifest URL: https://raw.githubusercontent.com/.../manifest.json?t=XXXXX
system: salvo=1.0.0  novo=1.0.1
ESP:    atual=0.1.4  novo=0.1.5  atualizar=SIM
Display:                          atualizar=SIM
Abrindo tela de confirmacao...
```

O operador confirma na tela 25 e o update segue:
1. Display atualiza (barra de progresso na tela)
2. ESP grava o novo firmware e reinicia

---
---

## Cenário 2 — Atualizar Apenas o Firmware ESP

> Use quando **não** mudou nenhum arquivo do display — só o código da ESP.

### Passo a passo

**1. Compile o novo firmware da ESP**
```
pio run --target release
```

---

**2. Calcule o MD5**
```powershell
Get-FileHash .pio\build\<env>\firmware.bin -Algorithm MD5
```

---

**3. Atualize o `manifest.json`**

Mude **apenas** estas três chaves — não toque em `display.version` nem em `display.files`:

```json
{
  "system_version": "1.0.2",        ← incrementa
  "version":        "0.1.6",        ← nova versão da ESP
  "md5":  "<novo hash>",
  "size_bytes": <novo tamanho>,

  "display": {
    "version": "1.0.1",             ← NÃO muda (mesmo valor de antes)
    "files": [ ... ]                ← NÃO muda
  }
}
```

> **Por que `display.version` fica igual?**
> A ESP compara `display.version` com o que está salvo na NVS.
> Se for igual, pula toda a etapa do display e vai direto para o flash da ESP.

---

**4. Suba para o GitHub**

```
WasherUpdate/
├── manifest.json     ← atualizado
└── firmware.bin      ← novo
```

Não precisa mexer na pasta `display/`.

---

**5. Verifique no Serial Monitor**
```
=== OTA: verificando manifest ===
system: salvo=1.0.1  novo=1.0.2
ESP:    atual=0.1.5  novo=0.1.6  atualizar=SIM
Display:                          atualizar=nao
Abrindo tela de confirmacao...
```

O operador confirma → ESP atualiza → reinicia. Display não é tocado.

---
---

## Referência rápida

| Campo             | Cenário 1 (tudo) | Cenário 2 (só ESP) |
|-------------------|-------------------|---------------------|
| `system_version`  | incrementa        | incrementa          |
| `version`         | incrementa        | incrementa          |
| `firmware.bin`    | substitui         | substitui           |
| `md5`             | recalcula         | recalcula           |
| `display.version` | incrementa        | **NÃO muda**        |
| `display/`        | atualiza arquivos | **NÃO muda**        |

---

## Checklist rápido antes de subir

- [ ] `system_version` é diferente do que está no dispositivo
- [ ] `version` bate com o `FW_VERSION` definido no `main.cpp`
- [ ] MD5 calculado sobre o `.bin` exato que foi upado no GitHub
- [ ] `size_bytes` confere com o tamanho real do arquivo
- [ ] `display.version` só mudou se arquivos do display foram alterados
- [ ] Branch `main` foi atualizada (não esqueceu de fazer push)
- [ ] Testou no Serial Monitor que a versão nova aparece no log
