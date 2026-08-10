"""Helpers de terminal compartilhados pelos CLIs."""

import ctypes
import os
import sys

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_GRAY = "\033[90m"


def enable_ansi_colors():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(out, ctypes.byref(mode)):
            kernel32.SetConsoleMode(out, mode.value | 0x0004)
    except Exception:
        pass


def c(text: str, color: str, no_color: bool = False) -> str:
    return text if no_color else f"{color}{text}{C_RESET}"


def log_info(msg: str, no_color: bool = False):
    print(f"  {c('[INFO]', C_BLUE, no_color)}  {msg}")


def log_ok(msg: str, no_color: bool = False):
    print(f"  {c('[ OK ]', C_GREEN, no_color)}  {msg}")


def log_warn(msg: str, no_color: bool = False):
    print(f"  {c('[WARN]', C_YELLOW, no_color)}  {msg}")


def log_error(msg: str, no_color: bool = False):
    print(f"  {c('[ERRO]', C_RED, no_color)}  {msg}", file=sys.stderr)


def print_banner(title: str, no_color: bool = False):
    bar = "=" * 60
    print(f"\n{c(bar, C_CYAN, no_color)}")
    print(
        f"  {c(title, C_BOLD + C_CYAN, no_color)} "
        f"{c('v' + __version__, C_GRAY, no_color)}"
    )
    print(f"{c(bar, C_CYAN, no_color)}\n")


def print_report_bar(title: str, no_color: bool = False):
    bar = "=" * 60
    print(f"\n{c(bar, C_CYAN, no_color)}")
    print(f"  {c(title, C_BOLD, no_color)}")
    print(f"{c(bar, C_CYAN, no_color)}")
