"""Bundle the Standard Context Pack JSON into the wheel.

The pack lives at ``schemas/`` in the repo root, outside this project, so a
static ``force-include`` only works when building from the repo. ``python -m
build`` builds the wheel *from the sdist*, where the repo root is gone. The
sdist therefore carries its own copy at ``schemas/`` (see pyproject.toml), and
this hook picks whichever copy exists.
"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_PACK = "standard-context-pack-v1.json"


class PackBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        candidates = [root / "../../schemas" / _PACK, root / "schemas" / _PACK]
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            raise FileNotFoundError(f"{_PACK} not found in: {[str(p) for p in candidates]}")
        build_data["force_include"][str(source.resolve())] = f"konstera_sdk_contexts/schemas/{_PACK}"
