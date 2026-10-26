"""Command line:

    python -m islandgen --seed 1 --layout 1 --target roblox            -> out/meta_1_roblox/
    python -m islandgen --seed 4 --layout 1 --climb 30 --pads 12 --out levels
    python -m islandgen --list                                          -> every setting, default and range

Any setting from islandgen.PARAMS can be passed as --name value.
"""
import argparse
import os
import time

from .meta import PARAMS, generate
from .export import write_meta
from .units import TARGETS


def main():
    p = argparse.ArgumentParser(prog="python -m islandgen", description="Generate floating land and export it.")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--target", default="roblox", choices=sorted(TARGETS), help="engine scale for the .obj (and chunking)")
    p.add_argument("--out", default="out", help="parent folder; writes <out>/meta_<seed>_<target>/")
    p.add_argument("--name", default=None, help="folder name instead of meta_<seed>_<target>")
    p.add_argument("--list", action="store_true", help="print every setting and exit")
    for group, items in PARAMS.items():
        g = p.add_argument_group(group)
        for k, (default, lo, hi, step, help_) in items.items():
            g.add_argument(f"--{k}", type=type(default), default=None, help=f"{help_} [{default}, {lo}..{hi}]")
    args = vars(p.parse_args())
    if args.pop("list"):
        for group, items in PARAMS.items():
            print(f"\n[{group}]")
            for k, (default, lo, hi, step, help_) in items.items():
                print(f"  --{k:<13} {default!s:>7}   ({lo}..{hi})  {help_}")
        return
    seed, target, out, name = args.pop("seed"), args.pop("target"), args.pop("out"), args.pop("name")
    settings = {k: v for k, v in args.items() if v is not None}
    t = time.perf_counter()
    res = generate(seed, settings)
    folder = write_meta(res, os.path.join(out, name or f"meta_{seed}_{target}"), target)
    st = res["stats"]
    print(f"wrote {folder}  ({st['tris']} tris, unreachable {st['unreachable']}, {time.perf_counter() - t:.1f}s)")
    if "links" in st:
        print("links:", st["links"])


if __name__ == "__main__":
    main()
