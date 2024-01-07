import logging
import sys
from argparse import ArgumentParser

from client.app import FileApp

from server.server import FileServer


def add_subparser_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="The host address to use",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=50_000, help="The port to use"
    )
    parser.add_argument("-v", "--verbose", action="store_true")


def main():
    parser = ArgumentParser()

    subparsers = parser.add_subparsers(dest="command")
    client = subparsers.add_parser("client", help="Client commands")
    server = subparsers.add_parser("server", help="Server commands")

    add_subparser_args(client)
    add_subparser_args(server)

    args = parser.parse_args(sys.argv[1:])

    logging.basicConfig(level=logging.INFO)

    if args.command == "client":
        app = FileApp()
        app.start()
    elif args.command == "server":
        server = FileServer(args.host, args.port)
        server.start()


if __name__ == "__main__":
    main()

