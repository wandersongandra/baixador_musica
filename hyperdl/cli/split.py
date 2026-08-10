"""CLI de separacao de faixas (antes: separar_faixas_audio.py)."""

import argparse
import sys
from pathlib import Path

from hyperdl.cli.common import (
    c,
    enable_ansi_colors,
    log_error,
    log_info,
    log_ok,
    print_banner,
    print_report_bar,
    C_BOLD,
    C_CYAN,
    C_GREEN,
    C_RED,
)
from hyperdl.core import splitter as sp
from hyperdl.core.utils import ensure_ffmpeg


def print_report(results: list[sp.SplitResult], nc: bool = False):
    total = len(results)
    success = sum(1 for r in results if r.success)
    failed = total - success
    total_tracks = sum(r.track_count for r in results)
    total_duration = sum(r.total_duration for r in results)
    total_time = sum(r.elapsed for r in results)

    print_report_bar("RELATORIO FINAL", nc)
    print(f"  Arquivos:  {total}")
    print(f"  {c('Sucesso:', C_GREEN, nc)} {success} | {c('Falha:', C_RED, nc)} {failed}")
    print(f"  Faixas:    {total_tracks}")
    print(f"  Duracao:   {total_duration:.1f}s de audio processado")
    print(f"  Tempo:     {total_time:.1f}s")

    if failed > 0:
        print(f"\n  {c('FALHAS:', C_RED, nc)}")
        for r in results:
            if not r.success:
                print(f"    - {r.input_file.name}: {r.error}")

    print(f"\n{c('=' * 60, C_CYAN, nc)}\n")


def make_progress_cb(nc: bool):
    def cb(pct: float, msg: str):
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "=" * filled + "-" * (bar_len - filled)
        print(
            f"\r  {c('[>>]', C_CYAN, nc)} {bar} {pct:.0f}% - {msg}  ",
            end="",
            flush=True,
        )

    return cb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="separar_faixas_audio",
        description="Cortador de musicas com deteccao de silencio profissional",
    )

    parser.add_argument("input", nargs="*", type=Path, help="Arquivo(s) de audio ou diretorio")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=Path(sp.DEFAULT_OUTPUT_DIR),
        help=f"Diretorio de saida (default: {sp.DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-t", "--threshold", default=sp.DEFAULT_THRESHOLD,
        help=f"Threshold de silencio em dB (default: {sp.DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "-ms", "--min-silence", type=float, default=sp.DEFAULT_MIN_SILENCE,
        help=f"Duracao minima de silencio em segundos (default: {sp.DEFAULT_MIN_SILENCE})",
    )
    parser.add_argument(
        "--min-track", type=float, default=sp.DEFAULT_MIN_TRACK,
        help=f"Duracao minima de faixa em segundos (default: {sp.DEFAULT_MIN_TRACK})",
    )
    parser.add_argument(
        "--lead-in", type=float, default=sp.DEFAULT_LEAD_IN,
        help=f"Segundos de audio antes do corte (default: {sp.DEFAULT_LEAD_IN})",
    )
    parser.add_argument(
        "--lead-out", type=float, default=sp.DEFAULT_LEAD_OUT,
        help=f"Segundos de audio apos o corte (default: {sp.DEFAULT_LEAD_OUT})",
    )
    parser.add_argument(
        "-f", "--format", default=sp.DEFAULT_FORMAT, choices=sorted(sp.FORMAT_CODEC_MAP.keys()),
        help=f"Formato de saida (default: {sp.DEFAULT_FORMAT})",
    )
    parser.add_argument("--bitrate", default="", help="Bitrate personalizado (ex: 192k)")
    parser.add_argument(
        "--prefix", default=sp.DEFAULT_PREFIX,
        help=f"Prefixo das faixas (default: {sp.DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--digits", type=int, default=sp.DEFAULT_DIGITS,
        help=f"Digitos na numeracao (default: {sp.DEFAULT_DIGITS})",
    )
    parser.add_argument("--adaptive", action="store_true", help="Threshold adaptativo automatico")
    parser.add_argument("--recursive", action="store_true", help="Buscar arquivos recursivamente em diretorios")
    parser.add_argument("--no-color", action="store_true", help="Desabilitar cores no terminal")

    return parser


def main() -> int:
    enable_ansi_colors()
    args = build_parser().parse_args()
    nc = args.no_color

    print_banner("Separador de Faixas", nc)

    if not ensure_ffmpeg():
        log_error("FFmpeg/FFprobe nao encontrado no PATH", nc)
        return 1

    config = sp.SplitConfig(
        output_dir=args.output_dir,
        threshold=args.threshold,
        min_silence=args.min_silence,
        min_track=args.min_track,
        lead_in=args.lead_in,
        lead_out=args.lead_out,
        fmt=args.format,
        bitrate=args.bitrate,
        prefix=args.prefix,
        digits=args.digits,
        adaptive=args.adaptive,
    )

    input_paths: list[Path] = []
    for p in args.input:
        if p.is_dir():
            found = sp.find_audio_files(p, args.recursive)
            if not found:
                log_error(f"Nenhum audio encontrado em: {p}", nc)
                continue
            input_paths.extend(found)
            log_info(f"Encontrados {len(found)} arquivos de audio", nc)
        elif p.is_file():
            input_paths.append(p)
        else:
            log_error(f"Arquivo nao encontrado: {p}", nc)

    if not input_paths:
        log_error("Nenhum arquivo de audio especificado. Use -h para ajuda.", nc)
        return 1

    results: list[sp.SplitResult] = []
    for i, filepath in enumerate(input_paths, 1):
        print(f"\n--- [{i}/{len(input_paths)}] {c(filepath.name, C_BOLD, nc)} ---")
        log_info(
            f"Threshold: {config.threshold} | Min silencio: {config.min_silence}s"
            f" | Min faixa: {config.min_track}s",
            nc,
        )

        result = sp.split_file(filepath, config, make_progress_cb(nc))
        print()
        if result.success:
            log_ok(
                f"{result.track_count} faixas em {result.elapsed:.1f}s -> "
                f"{result.output_dir}",
                nc,
            )
        else:
            log_error(f"Falha: {result.error}", nc)
        results.append(result)

    print_report(results, nc)

    failed = sum(1 for r in results if not r.success)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
