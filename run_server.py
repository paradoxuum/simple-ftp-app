from argparse import ArgumentParser
import sys
from server.server import FileServer


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="The host address the server should use",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=50_000, help="The port the server should use"
    )

    args = parser.parse_args(sys.argv[1:])

    server = FileServer(args.host, args.port)
    try:
        server.process()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()

