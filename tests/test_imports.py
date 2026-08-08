"""Smoke tests for the initial package structure."""

import importlib


def test_project_packages_import() -> None:
    """Each initial source package should import from the repository root."""
    module_names = (
        "src",
        "src.data",
        "src.features",
        "src.models",
        "src.evaluation",
    )

    for module_name in module_names:
        assert importlib.import_module(module_name) is not None
