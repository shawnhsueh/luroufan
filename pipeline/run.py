"""Run the full pipeline: discover -> extract -> build.

Every step is cached/incremental, so re-running only pays for new or changed data.
"""

import argparse

from . import build, discover, extract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-discover", action="store_true", help="reuse data/restaurants.jsonl and data/reviews.jsonl")
    parser.add_argument("--sync", action="store_true", help="rate with one request at a time instead of a batch")
    args = parser.parse_args()

    if not args.skip_discover:
        discover.main([])
    extract.main(["--sync"] if args.sync else [])
    build.main([])


if __name__ == "__main__":
    main()
