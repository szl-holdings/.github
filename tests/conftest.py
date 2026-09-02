"""Collection support for isolated Living Constellation operator tests."""
from __future__ import annotations

import importlib.util
import sys

_ORIGINAL_MODULE_FROM_SPEC = importlib.util.module_from_spec


def _registered_module_from_spec(spec):
    module = _ORIGINAL_MODULE_FROM_SPEC(spec)
    if getattr(spec, "name", None) == "hf_living_constellation_operator":
        sys.modules[spec.name] = module
    return module


importlib.util.module_from_spec = _registered_module_from_spec
