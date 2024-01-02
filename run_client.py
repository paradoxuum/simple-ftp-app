import sys
from argparse import ArgumentParser

from client.app import FileApp


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="The host address the client should use",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=50_000, help="The port the client should use"
    )

    args = parser.parse_args(sys.argv[1:])
    app = FileApp()
    app.start()


if __name__ == "__main__":
    main()
