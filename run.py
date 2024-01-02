import sys
from argparse import ArgumentParser

from client.app import FileApp
from server.server import FileServer


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="The host address to use",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=50_000, help="The port to use"
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("client", help="Client commands")
    subparsers.add_parser("server", help="Server commands")
    args = parser.parse_args(sys.argv[1:])

    if args.command == "client":
        app = FileApp()
        app.start()
    elif args.command == "server":
        server = FileServer(args.host, args.port)
        server.process()


if __name__ == "__main__":
    main()

