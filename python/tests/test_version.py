"""__version__ must report the installed distribution's version."""
from importlib.metadata import version

import konstera_sdk


def test_version_matches_distribution() -> None:
    assert konstera_sdk.__version__ == version("konstera-sdk")
