"""Command-line interface: `python -m client.cli --help` (run from the repo root)."""
import argparse
import os
from pathlib import Path

from client.client import CloudWeaveClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloudweave", description="CloudWeave object store client")
    parser.add_argument(
        "--url",
        default=os.environ.get("CLOUDWEAVE_URL", "http://localhost:8000"),
        help="Controller base URL",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="Upload a file")
    up.add_argument("path", type=Path)

    down = sub.add_parser("download", help="Download an object")
    down.add_argument("object_id")
    down.add_argument("destination", type=Path)

    sub.add_parser("list", help="List objects")

    meta = sub.add_parser("metadata", help="Show object metadata")
    meta.add_argument("object_id")

    rm = sub.add_parser("delete", help="Delete an object")
    rm.add_argument("object_id")

    sub.add_parser("cluster", help="Show cluster status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = CloudWeaveClient(args.url)
    try:
        if args.command == "upload":
            print(client.upload(args.path))
        elif args.command == "download":
            client.download(args.object_id, args.destination)
        elif args.command == "list":
            print(client.list_objects())
        elif args.command == "metadata":
            print(client.metadata(args.object_id))
        elif args.command == "delete":
            client.delete(args.object_id)
        elif args.command == "cluster":
            print(client.cluster_status())
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
