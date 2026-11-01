"""Command-line interface: `python -m client.cli --help` (run from the repo root)."""
import argparse
import json
import os
from pathlib import Path
import sys

from client.client import CloudWeaveClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloudweave", description="CloudWeave object store client")
    parser.add_argument(
        "--url",
        default=os.environ.get("CLOUDWEAVE_URL", "http://localhost:8000"),
        help="Controller base URL (default: http://localhost:8000)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # upload
    up = sub.add_parser("upload", help="Upload a file")
    up.add_argument("path", type=Path, help="Path to local file")
    up.add_argument("--metadata", default="{}", help="Custom metadata as JSON string (e.g. '{\"author\":\"alice\"}')")

    # download
    down = sub.add_parser("download", help="Download an object")
    down.add_argument("object_id", help="Object ID")
    down.add_argument("destination", type=Path, nargs="?", default=None, help="Destination file/folder path")

    # list
    ls = sub.add_parser("list", help="List objects")
    ls.add_argument("--offset", type=int, default=0, help="Pagination offset")
    ls.add_argument("--limit", type=int, default=100, help="Pagination limit")

    # metadata
    meta = sub.add_parser("metadata", help="Show object metadata")
    meta.add_argument("object_id", help="Object ID")

    # patch-metadata
    pm = sub.add_parser("patch-metadata", help="Update custom metadata without re-uploading file")
    pm.add_argument("object_id", help="Object ID")
    pm.add_argument("metadata_json", help="JSON string with custom metadata to update")

    # delete
    rm = sub.add_parser("delete", help="Delete an object")
    rm.add_argument("object_id", help="Object ID")

    # cluster
    sub.add_parser("cluster", help="Show cluster status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = CloudWeaveClient(args.url)
    try:
        if args.command == "upload":
            metadata = {}
            if args.metadata:
                try:
                    metadata = json.loads(args.metadata)
                except json.JSONDecodeError as e:
                    print(f"Error parsing metadata JSON: {e}", file=sys.stderr)
                    return 1
            result = client.upload(args.path, metadata=metadata)
            print(json.dumps(result, indent=2))

        elif args.command == "download":
            dest = args.destination or Path(f"./downloaded_{args.object_id}")
            client.download(args.object_id, dest)
            print(f"Object {args.object_id} downloaded to {dest}")

        elif args.command == "list":
            result = client.list_objects(offset=args.offset, limit=args.limit)
            print(json.dumps(result, indent=2))

        elif args.command == "metadata":
            result = client.metadata(args.object_id)
            print(json.dumps(result, indent=2))

        elif args.command == "patch-metadata":
            try:
                patch_data = json.loads(args.metadata_json)
            except json.JSONDecodeError as e:
                print(f"Error parsing metadata JSON: {e}", file=sys.stderr)
                return 1
            result = client.patch_metadata(args.object_id, patch_data)
            print(json.dumps(result, indent=2))

        elif args.command == "delete":
            client.delete(args.object_id)
            print(f"Object {args.object_id} deleted successfully.")

        elif args.command == "cluster":
            result = client.cluster_status()
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
