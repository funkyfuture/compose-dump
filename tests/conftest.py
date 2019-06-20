import os
from pathlib import Path
from shutil import rmtree
from subprocess import call
from tempfile import mkdtemp

from pytest import fixture

FIXTURES_PATH = Path(__file__).parent / "fixtures"
PROJECTS_PATH = FIXTURES_PATH / "projects"


class ProjectDir:
    def __init__(self, path):
        self.path = Path(path)
        self.added_files = set()
        self.added_folders = set()

    def __getattr__(self, item):
        return getattr(self.path, item)

    def __str__(self):
        return str(self.path)

    def __truediv__(self, other):
        return self.path / other

    def add_file(self, rel_path):
        result = self.path / rel_path
        result.touch()
        self.added_files.add(result)
        return result

    def add_folder(self, rel_path):
        result = self.path / rel_path
        result.mkdir()
        self.added_folders.add(result)
        return result

    def clean(self):
        for x in self.added_files:
            try:
                x.unlink()
            except Exception:
                pass
        for x in self.added_folders:
            try:
                x.rmdir()
            except Exception:
                pass


def pytest_addoption(parser):
    parser.addoption(
        "--keep-results",
        action="store_true",
        help="Keep integration tests' temporary directories.",
    )


def change_to_project_path(request):
    cwd = os.getcwd()
    project_name = request.function.__name__[len("test_") :].split(  # noqa: E203
        "__", 1
    )[0]
    project_path = PROJECTS_PATH / project_name
    os.chdir(str(project_path))
    return project_path, cwd


@fixture
def project_dir(request):
    project_path, cwd = change_to_project_path(request)
    project_dir = ProjectDir(project_path)
    yield project_dir
    project_dir.clean()
    os.chdir(cwd)


@fixture
def compose_down(request):
    yield None
    project_path, cwd = change_to_project_path(request)
    call(["docker-compose", "down"])
    os.chdir(cwd)


@fixture
def temp_dir(request):
    temp_dir = mkdtemp(prefix="compose_dump_test_")
    yield Path(temp_dir)
    if not request.config.option.keep_results:
        rmtree(temp_dir)
