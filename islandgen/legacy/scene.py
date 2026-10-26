"""A whole scene: layout + one island per slot. Still just data."""
from . import island as island_mod
from . import layout as layout_mod
from . import ribbon as ribbon_mod
from ..mesh import build_mesh


def split_settings(settings: dict):
    isl = {k: settings[k] for k in island_mod.PARAMS if k in settings}
    lay = {k: settings[k] for k in layout_mod.PARAMS if k in settings}
    rib = {k: settings[k] for k in ribbon_mod.PARAMS if k in settings}
    return isl, lay, rib


def generate_scene(seed: int, settings: dict = None) -> dict:
    settings = settings or {}
    isl, lay, rib = split_settings(settings)
    isl_full = {**island_mod.DEFAULTS, **isl}
    lay_full = {**layout_mod.DEFAULTS, **lay}
    rib_full = {**ribbon_mod.DEFAULTS, **rib}
    base_r = isl_full["radius"]
    islands = []
    spine = None
    if int(rib_full["ribbon"]):
        spine = ribbon_mod.make_spine(seed, lay_full, rib_full)
        islands.append({
            "id": "ribbon",
            "position": [0.0, 0.0, 0.0],
            "island": {"seed": seed, "top_y": 0.0, "bottom_y": 0.0, "top_outline": []},
            "mesh": ribbon_mod.build_ribbon(seed, lay_full, rib_full,
                                            isl_full["rim"], isl_full["jitter"]),
        })
    slots = layout_mod.generate_layout(seed, base_r, spine=spine,
                                       ribbon_width=rib_full["width"], **lay)
    for i, slot in enumerate(slots):
        data = island_mod.generate_island(slot["seed"], **{**isl, "radius": slot["radius"]})
        islands.append({
            "id": f"island_{i:02d}",
            "position": slot["position"],
            "island": data,
            "mesh": build_mesh(data),
        })
    return {
        "seed": seed,
        "settings": {**island_mod.DEFAULTS, **layout_mod.DEFAULTS, **ribbon_mod.DEFAULTS, **settings},
        "islands": islands,
    }


def all_params() -> dict:
    return {"ribbon": ribbon_mod.PARAMS, "layout": layout_mod.PARAMS, "island": island_mod.PARAMS}
