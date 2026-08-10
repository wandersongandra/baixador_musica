"""CLI de download do YouTube (antes: baixar_audio_youtube.py)."""

import argparse
import signal
import sys
from pathlib import Path

from hyperdl.cli.common import (
    c,
    enable_ansi_colors,
    log_error,
    log_info,
    log_ok,
    log_warn,
    print_banner,
    print_report_bar,
    C_BOLD,
    C_CYAN,
    C_GRAY,
    C_GREEN,
    C_RED,
)
from hyperdl.core import downloader as dl
from hyperdl.core.utils import ensure_ffmpeg, ensure_yt_dlp, format_bytes, format_duration

_interrupted = False


def _signal_handler(sig, frame):
    global _interrupted
    _interrupted = True


def print_report(stats: dl.DownloadStats, no_color: bool = False):
    print_report_bar("RELATORIO FINAL", no_color)
    print(f"  Total:    {stats.total}")
    print(f"  {c('Sucesso:', C_GREEN, no_color)} {stats.success}")
    print(f"  {c('Falha:', C_RED, no_color)}    {stats.failed}")
    print(f"  Pulados:  {stats.skipped}")
    print(f"  Tamanho:  {format_bytes(stats.total_bytes)}")
    print(f"  Tempo:    {format_duration(stats.total_time)}")

    if stats.failed > 0:
        print(f"\n  {c('FALHAS:', C_RED, no_color)}")
        for r in stats.results:
            if not r.success:
                print(f"    - {r.url}")
                print(f"      {c(r.error or 'desconhecido', C_GRAY, no_color)}")

    print(f"\n{c('=' * 60, C_CYAN, no_color)}\n")


def make_progress_cb(no_color: bool):
    def cb(p: dl.DownloadProgress):
        if p.status == "downloading":
            bar_len = 30
            filled = int(bar_len * p.percent / 100)
            bar = "=" * (filled - 1) + ">" if filled > 0 else ""
            bar += "-" * (bar_len - filled)
            speed = f"{format_bytes(p.speed)}/s" if p.speed else "?"
            eta = format_duration(p.eta) if p.eta else "?"
            line = (
                f"\r  {c('[>>]', C_CYAN, no_color)} "
                f"[{p.index}/{p.total}] "
                f"{p.percent:5.1f}% "
                f"[{bar}] "
                f"{format_bytes(p.downloaded)}/{format_bytes(p.total_bytes)} "
                f"| {speed} | ETA: {eta}  "
            )
            print(line, end="", flush=True)
        elif p.status == "finished":
            print()
            log_ok(p.title, no_color)
        elif p.status == "processing":
            log_info(f"Processando: {p.title}", no_color)

    return cb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baixar_audio_youtube",
        description="Baixador de midia YouTube com qualidade maxima",
        epilog=(
            "Exemplos:\n"
            "  %(prog)s https://www.youtube.com/watch?v=ABC123\n"
            "  %(prog)s --audio-format flac URL\n"
            "  %(prog)s --batch links.txt --playlist\n"
            "  %(prog)s --archive historico.txt URL\n"
            "  %(prog)s --simulate --write-info-json URL\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("urls", nargs="*", help="URL(s) do YouTube")
    parser.add_argument(
        "-m", "--mode", choices=["audio", "video"], default="audio",
        help="Modo de download (default: audio)",
    )
    parser.add_argument(
        "-af", "--audio-format", choices=sorted(dl.AUDIO_FORMATS),
        default=dl.DEFAULT_AUDIO_FMT,
        help=f"Formato do audio (default: {dl.DEFAULT_AUDIO_FMT})",
    )
    parser.add_argument(
        "-aq", "--audio-quality", default=dl.DEFAULT_AUDIO_QUAL,
        help="Qualidade do audio 0=best, 9=worst (default: 0)",
    )
    parser.add_argument(
        "-vq", "--video-quality", choices=sorted(dl.VIDEO_QUALS),
        default=dl.DEFAULT_VIDEO_QUAL,
        help=f"Qualidade maxima do video (default: {dl.DEFAULT_VIDEO_QUAL})",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=dl.DEFAULT_OUTPUT_DIR,
        help=f"Diretorio de saida (default: {dl.DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--template", default=dl.DEFAULT_TEMPLATE,
        help=f"Template de nome de arquivo (default: {dl.DEFAULT_TEMPLATE.replace('%', '%%')})",
    )
    parser.add_argument("-p", "--playlist", action="store_true", help="Baixar playlist inteira")
    parser.add_argument("--playlist-items", help="Itens da playlist (ex: 1-10, 15, 20-)")
    parser.add_argument(
        "--cookies-from-browser", choices=sorted(dl.BROWSER_LIST),
        help="Extrair cookies do navegador",
    )
    parser.add_argument("--cookies-file", type=Path, help="Arquivo de cookies (Netscape format)")
    parser.add_argument("--proxy", help="Proxy (ex: http://127.0.0.1:8080)")
    parser.add_argument("--rate-limit", help="Limite de velocidade (ex: 10M)")
    parser.add_argument(
        "-r", "--retries", type=int, default=dl.DEFAULT_RETRIES,
        help=f"Tentativas por video (default: {dl.DEFAULT_RETRIES})",
    )
    parser.add_argument(
        "-c", "--concurrent", type=int, default=dl.DEFAULT_CONCURRENT,
        help=f"Fragmentos paralelos (default: {dl.DEFAULT_CONCURRENT})",
    )
    parser.add_argument("--allow-overwrites", action="store_true", help="Sobrescrever arquivos existentes")
    parser.add_argument("--no-embed-metadata", action="store_false", dest="embed_metadata", help="Nao incorporar metadados")
    parser.add_argument("--no-embed-thumbnail", action="store_false", dest="embed_thumbnail", help="Nao incorporar thumbnail")
    parser.add_argument("--write-thumbnail", action="store_true", help="Salvar thumbnail como arquivo separado")
    parser.add_argument("--write-info-json", action="store_true", help="Salvar metadados em JSON")
    parser.add_argument("--no-restrict-filenames", action="store_false", dest="restrict_filenames", help="Nao restringir caracteres no nome do arquivo")
    parser.add_argument("--trim-filenames", type=int, metavar="N", help="Limitar nome do arquivo a N caracteres")
    parser.add_argument("--sponsorblock", action="store_true", help="Remover segmentos patrocinados")
    parser.add_argument("-a", "--archive", type=Path, help="Arquivo de historico de downloads")
    parser.add_argument("--simulate", action="store_true", help="Simular sem baixar")
    parser.add_argument("--sleep-requests", type=float, default=0.0, help="Pausa entre requisicoes (segundos)")
    parser.add_argument("--sleep-interval", type=float, default=0.0, help="Pausa entre downloads (segundos)")
    parser.add_argument("-b", "--batch", type=Path, help="Arquivo com URLs (uma por linha, # = comentario)")
    parser.add_argument("--verbose", action="store_true", help="Modo verbose")
    parser.add_argument("--no-color", action="store_true", help="Desabilitar cores no terminal")

    return parser


def main() -> int:
    enable_ansi_colors()
    global _interrupted
    signal.signal(signal.SIGINT, _signal_handler)

    args = build_parser().parse_args()
    print_banner("Hyper Downloader", args.no_color)

    if not ensure_yt_dlp():
        log_error("yt-dlp nao instalado. Execute: pip install yt-dlp", args.no_color)
        return 1
    if not ensure_ffmpeg():
        log_warn("FFmpeg nao encontrado. Conversao pode falhar.", args.no_color)

    config = dl.DownloadConfig(
        mode=dl.DownloadMode(args.mode),
        audio_format=args.audio_format,
        audio_quality=args.audio_quality,
        video_quality=args.video_quality,
        output_dir=args.output,
        template=args.template,
        playlist=args.playlist,
        playlist_items=args.playlist_items,
        cookies_from_browser=args.cookies_from_browser,
        cookies_file=args.cookies_file,
        proxy=args.proxy,
        rate_limit=args.rate_limit,
        retries=args.retries,
        concurrent=args.concurrent,
        no_overwrites=not args.allow_overwrites,
        embed_metadata=args.embed_metadata,
        embed_thumbnail=args.embed_thumbnail,
        write_thumbnail=args.write_thumbnail,
        write_info_json=args.write_info_json,
        restrict_filenames=args.restrict_filenames,
        trim_filenames=args.trim_filenames,
        sponsorblock=args.sponsorblock,
        archive=args.archive,
        simulate=args.simulate,
        sleep_requests=args.sleep_requests,
        sleep_interval=args.sleep_interval,
        verbose=args.verbose,
    )

    urls = list(args.urls)

    if args.batch:
        if not args.batch.exists():
            log_error(f"Arquivo batch nao encontrado: {args.batch}", args.no_color)
            return 1
        batch_lines = args.batch.read_text(encoding="utf-8").splitlines()
        batch_urls = [
            line.strip()
            for line in batch_lines
            if line.strip() and not line.strip().startswith("#")
        ]
        urls.extend(batch_urls)
        log_info(f"Carregadas {len(batch_urls)} URLs do batch", args.no_color)

    if not urls:
        log_error("Nenhuma URL fornecida. Use -h para ajuda.", args.no_color)
        return 1

    log_info(f"Modo: {c(config.mode.value.upper(), C_BOLD, args.no_color)}", args.no_color)
    log_info(f"Saida: {config.output_dir}", args.no_color)
    log_info(f"URLs: {len(urls)}", args.no_color)
    if config.archive:
        log_info(f"Arquivo: {config.archive}", args.no_color)
    if config.simulate:
        log_warn("MODO SIMULACAO — nada sera baixado", args.no_color)

    print()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    stats = dl.download_urls(
        urls,
        config,
        progress=make_progress_cb(args.no_color),
        is_cancelled=lambda: _interrupted,
    )
    print_report(stats, args.no_color)

    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
