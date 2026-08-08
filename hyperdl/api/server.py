"""Entry point do servidor web."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(prog="hyperdl-server", description="Hyper Downloader Web")
    parser.add_argument("--host", default="127.0.0.1", help="Endereco (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta (default: 8000)")
    parser.add_argument("--no-reload", action="store_true", help="Desabilitar reload")
    args = parser.parse_args()

    uvicorn.run(
        "hyperdl.api.app:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
