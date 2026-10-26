"""Nox sessions: lint, format, typecheck, deps, tests.

All sessions install the project plus its `dev` and `test` extras so the tool
versions stay in sync with `pyproject.toml`.
"""

import nox

nox.options.default_venv_backend = "uv"

PYTHON = "3.13"
SOURCES = ["src", "tests", "scripts", "noxfile.py", "setup_cython.py", "cups/brhl3040cn-filter"]
TYPECHECK_SOURCES = ["src", "tests", "noxfile.py", "cups/brhl3040cn-filter"]


@nox.session(python=PYTHON)
def lint(session: nox.Session) -> None:
    """Run the ruff linter."""
    session.install(".[dev]")
    session.run("ruff", "check", *SOURCES)


@nox.session(python=PYTHON)
def format_check(session: nox.Session) -> None:
    """Verify formatting (ruff format --check)."""
    session.install(".[dev]")
    session.run("ruff", "format", "--check", *SOURCES)


@nox.session(python=PYTHON)
def format(session: nox.Session) -> None:
    """Auto-format and apply safe lint fixes."""
    session.install(".[dev]")
    session.run("ruff", "format", *SOURCES)
    session.run("ruff", "check", "--fix", *SOURCES)


@nox.session(python=PYTHON)
def typecheck(session: nox.Session) -> None:
    """Run the pyrefly type checker."""
    session.install(".[dev,test]")
    session.run("pyrefly", "check", *TYPECHECK_SOURCES)


@nox.session(python=PYTHON)
def deps(session: nox.Session) -> None:
    """Check declared dependencies against imports (deptry)."""
    session.install(".[dev]")
    session.run("deptry", ".")


@nox.session(python=["3.11", "3.13"])
def tests(session: nox.Session) -> None:
    """Run the test suite on the oldest supported Python (Debian 12) and the newest."""
    session.install(".[test]")
    session.run("pytest", *session.posargs)
