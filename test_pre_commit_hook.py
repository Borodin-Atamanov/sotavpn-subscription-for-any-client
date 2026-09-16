"""Checks for the pre-commit version hook and the version prints.

Run them with:
    python3 -m unittest test_pre_commit_hook

The hook is exercised against temporary git repositories built on the
spot; the real repository of the program is never touched.
"""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import install_sotavpn_bridge as installer
import settings

REPOSITORY_ROOT = Path(__file__).resolve().parent
HOOK_FILE = REPOSITORY_ROOT / "hooks" / "pre-commit"


def load_the_hook_module():
    """Load hooks/pre-commit, which carries no .py suffix, as a module."""
    loader = SourceFileLoader("pre_commit_hook_of_the_repository", str(HOOK_FILE))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


hook = load_the_hook_module()


class BumpVersionCheck(unittest.TestCase):
    """The version arithmetic and the rewrite of the settings file."""

    def a_settings_file(self, text):
        directory = tempfile.mkdtemp(prefix="bridge-bump-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = Path(directory) / "settings.py"
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_next_version_raises_the_third_number(self):
        self.assertEqual(hook.get_next_version("1.1.21"), "1.1.22")
        self.assertEqual(hook.get_next_version("0.0.9"), "0.0.10")

    def test_a_version_that_is_not_a_triple_is_refused(self):
        for value in ("1.1", "1.1.s21", "one.two.three", ""):
            with self.assertRaises(ValueError, msg=value):
                hook.get_next_version(value)

    def test_the_bump_rewrites_the_version_line_only(self):
        path = self.a_settings_file('PROGRAM_VERSION = "1.1.21"\nPROGRAM_NAME = "x"\n')
        self.assertEqual(hook.bump_settings_version(path), "1.1.22")
        self.assertEqual(path.read_text(encoding="utf-8"), 'PROGRAM_VERSION = "1.1.22"\nPROGRAM_NAME = "x"\n')

    def test_a_settings_file_without_the_version_line_is_refused(self):
        path = self.a_settings_file('PROGRAM_NAME = "x"\n')
        with self.assertRaises(ValueError):
            hook.bump_settings_version(path)


class PreCommitHookCheck(unittest.TestCase):
    """The hook in temporary git repositories, exactly as git runs it."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="bridge-hook-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.run_git("init", "-q")
        self.run_git("config", "user.email", "check@example.com")
        self.run_git("config", "user.name", "Check")
        (self.directory / "settings.py").write_text('PROGRAM_VERSION = "0.1.0"\n', encoding="utf-8")
        (self.directory / "hooks").mkdir()
        shutil.copy2(HOOK_FILE, self.directory / "hooks" / "pre-commit")
        os.chmod(self.directory / "hooks" / "pre-commit", 0o755)
        self.run_git("add", "-A")
        self.run_git("commit", "-q", "-m", "initial")
        self.run_git("config", "core.hooksPath", str(self.directory / "hooks"))

    def run_git(self, *arguments):
        finished = subprocess.run(
            ["git", *arguments], cwd=self.directory, capture_output=True, text=True, check=False
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        return finished

    def add_a_file_and_commit(self, name):
        (self.directory / name).write_text(f"{name}\n", encoding="utf-8")
        self.run_git("add", name)
        self.run_git("commit", "-q", "-m", f"add {name}")

    def committed_settings(self):
        return self.run_git("show", "HEAD:settings.py").stdout

    def test_the_hook_file_of_the_repository_is_executable(self):
        self.assertTrue(os.access(HOOK_FILE, os.X_OK), HOOK_FILE)

    def test_a_commit_carries_the_next_version(self):
        self.add_a_file_and_commit("a.txt")
        self.assertIn('PROGRAM_VERSION = "0.1.1"', self.committed_settings())

    def test_every_commit_raises_the_number_once(self):
        for name in ("a.txt", "b.txt", "c.txt"):
            self.add_a_file_and_commit(name)
        self.assertIn('PROGRAM_VERSION = "0.1.3"', self.committed_settings())

    def test_a_broken_version_line_does_not_block_a_commit(self):
        (self.directory / "settings.py").write_text('PROGRAM_VERSION = "1.1.s21"\n', encoding="utf-8")
        (self.directory / "b.txt").write_text("b\n", encoding="utf-8")
        self.run_git("add", "settings.py", "b.txt")
        finished = subprocess.run(
            ["git", "commit", "-m", "broken"], cwd=self.directory, capture_output=True, text=True, check=False
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("1.1.s21", self.committed_settings())
        self.assertIn("pre-commit", finished.stderr)

    def test_a_missing_hook_file_does_not_block_a_commit(self):
        (self.directory / "hooks" / "pre-commit").unlink()
        self.add_a_file_and_commit("a.txt")
        self.assertIn('PROGRAM_VERSION = "0.1.0"', self.committed_settings())


class VersionPrintCheck(unittest.TestCase):
    """Where the version is printed: the installer output and the program journal."""

    def test_the_installer_prints_its_version_first(self):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            installer.main(["install_sotavpn_bridge.py", "frobnicate"])
        first_line = captured.getvalue().splitlines()[0]
        self.assertEqual(first_line, f"{settings.INSTALL_NAME} installer version {settings.PROGRAM_VERSION}")

    def test_the_program_names_the_version_when_it_stops(self):
        program_source = (REPOSITORY_ROOT / f"{settings.PROGRAM_NAME}.py").read_text(encoding="utf-8")
        self.assertIn(
            f'tell(f"the ports are closed, {{settings.PROGRAM_NAME}} version {{settings.PROGRAM_VERSION}} stops")',
            program_source,
        )
