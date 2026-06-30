"""Scale the npz dataset up to a target case count by hardlinking existing cases."""

import argparse
import os
import random
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--marker", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    d = Path(args.dir)
    sources = sorted(d.glob("case_*_x.npz"))
    n = len(sources)
    if n == 0:
        raise SystemExit(f"no source cases in {d}")
    rng = random.Random(args.seed)
    for i in range(n, args.total):
        src_x = sources[rng.randrange(n)]
        src_y = src_x.with_name(src_x.name.replace("_x.npz", "_y.npz"))
        dst_x = d / f"case_{i:05d}_x.npz"
        dst_y = d / f"case_{i:05d}_y.npz"
        if not dst_x.exists():
            os.link(src_x, dst_x)
        if not dst_y.exists():
            os.link(src_y, dst_y)
    Path(args.marker).write_text(f"{args.total}\n")
    print(f"scaled {d} to {args.total} cases")


if __name__ == "__main__":
    main()
