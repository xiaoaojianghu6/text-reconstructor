"""PyInstaller entry point for Text Reconstructor API server."""

import sys


def main():
    from text_reconstructor.api import start_server

    port = 18231
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port=port)


if __name__ == "__main__":
    main()
