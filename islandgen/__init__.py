"""islandGen - engine-agnostic procedural floating land for platformers.

    from islandgen import generate, write_meta
    res = generate(seed=1, settings={"layout": 1})          # 1 = tower, 0 = rings
    write_meta(res, "out/my_level", target="roblox")         # land.glb, land_roblox.obj, scene.json, level.json, chunks/

Everything inside is meters, Y up. Only the exporters know about engines.
Settings and their ranges: islandgen.PARAMS (the GUI's sliders come from it).
"""
from .meta import generate, PARAMS, DEFAULTS
from .export import write_meta
from .units import TARGETS

__all__ = ["generate", "write_meta", "PARAMS", "DEFAULTS", "TARGETS"]
__version__ = "0.3.0"
