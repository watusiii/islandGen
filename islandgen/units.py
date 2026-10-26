"""Units + axes. The generator works in METERS, Y UP, right-handed (the glTF convention).
Engines differ only in scale and which axis is up; exporters bake that in per target.

  engine    1 unit      up    notes
  unity     1 m         Y     imports .obj / .glb (glTFast) and handles handedness itself
  blender   1 m         Z     its .obj/.glb importers convert Y-up -> Z-up automatically
  unreal    1 cm        Z     its .glb importer converts axes; .obj gets cm baked in
  roblox    1 stud      Y     1 stud = 0.28 m (Roblox's own figure)
"""

STUD = 0.28  # meters per Roblox stud

TARGETS = {
    "unity":   {"scale": 1.0,        "unit": "m",    "up": "y"},
    "blender": {"scale": 1.0,        "unit": "m",    "up": "y (importer converts to z)"},
    "unreal":  {"scale": 100.0,      "unit": "cm",   "up": "y (importer converts to z)"},
    "roblox":  {"scale": 1.0 / STUD, "unit": "stud", "up": "y", "max_tris": 10000},  # cap ~20k per mesh; stay well under
}


def scale_for(target: str) -> float:
    return TARGETS[target]["scale"]
