<div align="center">

# ⚡ Hyper Downloader

**Baixe músicas e vídeos do YouTube e separe faixas automaticamente pela detecção de silêncio**

Interface Web moderna • CLI completa • Motores poderosos com `yt-dlp` + `FFmpeg`

[Instalação](#-instalação) • [Interface Web](#-interface-web) • [CLI](#-cli) • [Como funciona](#-como-funciona) • [Testes](#-testes)

</div>

---

## ✨ Funcionalidades

### 📥 Download do YouTube
- **Áudio** em MP3, M4A, FLAC, AAC, OPUS, WAV e Vorbis — com qualidade ajustável (`0` melhor a `9` pior)
- **Vídeo** em até 2160p (4K), escolhendo a qualidade máxima desejada
- **Playlists completas** ou seleção de itens (`--playlist-items "1-10, 15"`)
- **Busca por texto** (`ytsearch:...`) e suporte a múltiplas URLs por vez
- **SponsorBlock**: remove patrocínios, intros, outros e self-promo automaticamente
- **Metadados e capa** incorporados ao arquivo
- **Histórico** com arquivo de archive (não baixa duas vezes o mesmo vídeo)
- **Cookies do navegador** para vídeos com restrição de idade ou autenticação
- **Simulação** (`--simulate`) e **modo verbose** para depuração

### ✂️ Separação de faixas por silêncio
- Detecta silêncios com FFmpeg (`silencedetect`) e corta cada música automaticamente
- **Threshold adaptativo**: calcula o limiar ideal com base no volume médio do áudio
- Controles finos: silêncio mínimo, duração mínima da faixa, entrada/saída (lead-in/out)
- Formatos de saída: MP3, FLAC, M4A, AAC, OPUS, WAV e OGG
- **Bitrate personalizado** (ex: `192k`)
- Processamento em lote de diretórios inteiros (com `--recursive`)

### 🌐 Interface Web
- Painel com 3 abas: **Baixar**, **Separar Faixas** e **Arquivos**
- **Fila de processos em tempo real** com barra de progresso, velocidade, ETA e cancelamento
- **Arrastar e soltar** arquivos de áudio para o separador
- **Navegador de arquivos** com download direto dos resultados
- Preferências persistidas em `settings.json`

---

## 🚀 Instalação

### Pré-requisitos

| Dependência | Motivo | Instalação |
|---|---|---|
| **Python 3.10+** | Runtime | [python.org](https://www.python.org/downloads/) |
| **FFmpeg + FFprobe** | Conversão e detecção de silêncio | `winget install ffmpeg` / `choco install ffmpeg` |

> ⚠️ Sem FFmpeg o download de áudio e a separação de faixas **não funcionam** (o servidor avisa no painel de saúde).

### Passo a passo

```bash
# 1. Crie e ative o ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 2. Instale as dependencias
pip install -r requirements.txt

# 3. (Opcional) Instale como pacote — ganha os comandos abaixo
pip install -e .
```

Verifique se tudo está no lugar:

```bash
python -c "import yt_dlp, fastapi; print('ok')"
ffmpeg -version
```

---

## 🌐 Interface Web

```bash
python run_server.py              # ou: python -m hyperdl.api.server
```

Abra **http://127.0.0.1:8000** no navegador.

| Opção | Descrição |
|---|---|
| `--host 0.0.0.0` | Escuta em todas as interfaces (acessível na rede) |
| `--port 8080` | Porta alternativa |
| `--reload` | Recarrega automaticamente (desenvolvimento) |

### Uso rápido

1. **Baixar**: cole uma ou mais URLs (uma por linha), escolha modo/qualidade e clique em **Baixar**
2. **Separar Faixas**: arraste um áudio para a área de upload (ou informe o caminho no servidor), ajuste o threshold e clique em **Separar Faixas**
3. **Arquivos**: navegue, baixe e envie resultados direto para o separador

> 💡 O status das dependências (FFmpeg/yt-dlp) aparece no topo da página.

---

## ⌨️ CLI

### Download (`hyperdl-youtube` / `baixar_audio_youtube.py`)

```bash
# Áudio MP3 na melhor qualidade
python baixar_audio_youtube.py "https://www.youtube.com/watch?v=..." 

# Áudio FLAC com qualidade personalizada
python baixar_audio_youtube.py --audio-format flac --audio-quality 0 URL

# Vídeo em até 1080p com metadados
python baixar_audio_youtube.py --mode video --video-quality 1080 URL

# Playlist inteira removendo patrocinios
python baixar_audio_youtube.py --playlist --sponsorblock "https://www.youtube.com/playlist?list=..."

# Lote de URLs a partir de um arquivo + historico
python baixar_audio_youtube.py --batch links.txt --archive historico.txt

# Simular sem baixar (teste rapido)
python baixar_audio_youtube.py --simulate URL
```

| Opção principal | Descrição |
|---|---|
| `-m, --mode` | `audio` (padrão) ou `video` |
| `-af, --audio-format` | `mp3`, `m4a`, `aac`, `flac`, `opus`, `wav`, `vorbis` |
| `-aq, --audio-quality` | `0` (melhor) a `9` (pior) |
| `-vq, --video-quality` | `best`, `360`, `480`, `720`, `1080`, `1440`, `2160` |
| `-o, --output` | Diretório de saída (padrão: `downloads/`) |
| `-p, --playlist` | Baixa a playlist inteira |
| `--playlist-items` | Itens da playlist (ex: `1-10, 15, 20-`) |
| `--sponsorblock` | Remove patrocínios, intros e outros |
| `-a, --archive` | Arquivo de histórico (não repete downloads) |
| `--cookies-from-browser` | `chrome`, `edge`, `firefox`, `brave`, ... |
| `-r, --retries` | Tentativas por vídeo (padrão: 10) |
| `-c, --concurrent` | Fragmentos paralelos (padrão: 4) |
| `--simulate` | Simula sem baixar nada |

### Separar faixas (`hyperdl-split` / `separar_faixas_audio.py`)

```bash
# Corta um album em faixas
python separar_faixas_audio.py album.mp3

# Vários arquivos + diretorio inteiro com subpastas
python separar_faixas_audio.py musica1.flac --recursive ./albums

# Threshold personalizado e formato FLAC
python separar_faixas_audio.py album.mp3 --threshold -35dB --format flac

# Threshold adaptativo automatico + bitrate + ajuste fino
python separar_faixas_audio.py album.mp3 --adaptive --bitrate 192k --lead-in 0.3 --lead-out 0.3
```

| Opção | Descrição | Padrão |
|---|---|---|
| `-t, --threshold` | Limiar de silêncio em dB | `-40dB` |
| `-ms, --min-silence` | Silêncio mínimo para cortar (s) | `1.0` |
| `--min-track` | Duração mínima da faixa (s) | `5.0` |
| `--lead-in` / `--lead-out` | Margem antes/depois do corte (s) | `0.15` |
| `-f, --format` | `mp3`, `flac`, `m4a`, `aac`, `opus`, `wav`, `ogg` | `mp3` |
| `--bitrate` | Bitrate de saída (ex: `192k`) | automático |
| `--prefix` / `--digits` | Nome das faixas (ex: `faixa_01.mp3`) | `faixa` / `2` |
| `--adaptive` | Threshold automático pelo volume médio | desligado |
| `--recursive` | Busca em subpastas | desligado |

---

## 🗂️ Estrutura do projeto

```
.
├── hyperdl/                  # Pacote principal
│   ├── core/                 # Motores (sem dependencia de UI)
│   │   ├── downloader.py     #   Download via yt-dlp (playlists, archive, progresso)
│   │   ├── splitter.py       #   Deteccao de silencio e corte com FFmpeg
│   │   └── utils.py          #   Helpers (ffmpeg/yt-dlp, formatadores)
│   ├── cli/                  # Interfaces de linha de comando
│   │   ├── youtube.py        #   Download (argparse completo)
│   │   ├── split.py          #   Separacao de faixas
│   │   └── common.py         #   Cores, banner e logs
│   ├── api/                  # Servidor web (FastAPI)
│   │   ├── app.py            #   Rotas: download/split/jobs/settings/health
│   │   ├── files.py          #   Navegacao, upload e download de arquivos
│   │   ├── jobs.py           #   Fila de processos em memoria
│   │   ├── schemas.py        #   Modelos Pydantic com validacao
│   │   └── server.py         #   Entry point do uvicorn
│   ├── web/static/           # Front-end (HTML + CSS + JS vanilla)
│   ├── settings.py           # Preferencias persistidas (settings.json)
│   └── __init__.py
├── tests/                    # Testes (pytest, 15 testes)
├── baixar_audio_youtube.py   # Wrapper raiz (compatibilidade)
├── separar_faixas_audio.py   # Wrapper raiz (compatibilidade)
├── run_server.py             # Wrapper raiz do servidor
├── requirements.txt          # Dependencias para pip install
└── pyproject.toml            # Empacotamento e comandos
```

```
downloads/          # Midia baixada
  └── uploads/      # Audios enviados pela web
separado/           # Faixas separadas (uma pasta por album)
settings.json       # Preferencias da interface web (gerado automaticamente)
```

---

## ⚙️ API (para integrações)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/health` | Status do servidor e dependências |
| `GET` | `/api/defaults` | Valores padrão e formatos suportados |
| `GET/PUT` | `/api/settings` | Lê/atualiza preferências (PUT parcial) |
| `POST` | `/api/download` | Enfileira um download `{urls, mode, ...}` |
| `POST` | `/api/split` | Enfileira uma separação `{file, threshold, ...}` |
| `GET` | `/api/jobs` | Lista processos (estado, progresso, resultados) |
| `POST` | `/api/jobs/{id}/cancel` | Cancela um processo |
| `DELETE` | `/api/jobs/{id}` | Remove um processo da fila |
| `GET` | `/api/files` | Lista arquivos do servidor |
| `POST` | `/api/files/upload` | Envia um áudio |
| `GET` | `/api/files/download` | Baixa um arquivo |

Exemplo:

```bash
# Baixar audio
curl -X POST http://127.0.0.1:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.youtube.com/watch?v=..."], "mode": "audio", "audio_format": "mp3"}'
```

---

## 🧪 Testes

```bash
python -m pytest -q
```

> Os testes de separação geram áudio sintético com FFmpeg e usam apenas diretórios temporários — nada é gravado no projeto.

---

## 🛠️ Solução de problemas

| Problema | Solução |
|---|---|
| **"FFmpeg nao encontrado"** | Instale o FFmpeg e garanta que está no `PATH` |
| **Download falha com 403** | Atualize o yt-dlp: `pip install -U yt-dlp` |
| **Vídeo com restrição de idade** | Use `--cookies-from-browser chrome` |
| **Rate limited (429)** | Aguarde alguns minutos ou use `--proxy` |
| **Nenhuma faixa detectada no split** | Aumente o threshold (ex: `-30dB`) ou reduza o silêncio mínimo |

---

## 📜 Licença

Uso pessoal/educacional. Baixe apenas conteúdo com permissão dos detentores de direitos.
