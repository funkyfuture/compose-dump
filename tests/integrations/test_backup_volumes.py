from pathlib import Path
from subprocess import call
import tarfile
from tempfile import TemporaryDirectory

from pytest import mark
import yaml

from tests.utils import count_dir_contents, get_target_folder, result_okay


@mark.usefixtures("compose_down", "project_dir")
@mark.parametrize("compression", ("", "tar", "gz", "bz2", "xz"))
def test_volumes(compression, temp_dir):
    assert call(["docker", "volume", "create", "--name=dontcare"]) == 0
    assert call(["docker-compose", "up", "-d"]) == 0

    args = ["backup", "-t", str(temp_dir)]
    if compression:
        args.extend(["--compression", compression])

    assert result_okay(args)

    target_item = get_target_folder(temp_dir)

    if compression:
        assert target_item.is_file()
        with TemporaryDirectory() as target_folder:
            archive = tarfile.open(str(target_item))
            archive.extractall(target_folder)
            check_volumes_result(Path(target_folder))
    else:
        assert target_item.is_dir()
        target_folder = target_item
        check_volumes_result(target_folder)


def check_volumes_result(target_folder):
    with (target_folder / "Manifest.yml").open("rt") as f:
        manifest = next(yaml.load_all(f))
    volumes = manifest["volumes"]
    assert len(volumes["project"]) == 1
    volume = volumes["project"]["care"]
    assert volume == "care.tar"
    archive = target_folder / "volumes" / "project" / volume
    assert archive.is_file()
    assert tarfile.is_tarfile(str(archive))
    assert count_dir_contents(target_folder / "volumes" / "project") == 1
    assert len(volumes["services"]) == 1
    assert len(volumes["services"]["foo"]) == 2
    assert "/volume" in volumes["services"]["foo"], volumes["services"]["foo"]
    volume = volumes["services"]["foo"]["/volume"]
    archive = target_folder / "volumes" / "services" / volume
    assert archive.is_file()
    assert tarfile.is_tarfile(str(archive))
    volume = volumes["services"]["foo"]["/image_volume1"]
    archive = target_folder / "volumes" / "services" / volume
    assert archive.is_file()
    assert tarfile.is_tarfile(str(archive))
    assert count_dir_contents(target_folder / "volumes" / "services") == 2
    assert len(volumes["mounted"]) == 3
    assert (target_folder / "volumes" / "mounted" / "asset.txt").is_file()
    assert (target_folder / "volumes" / "mounted" / "assets").is_dir()
    assert (target_folder / "volumes" / "mounted" / "assets" / "dummy").is_file()
    assert (target_folder / "volumes" / "mounted" / "local").is_dir()
    assert (target_folder / "volumes" / "mounted" / "local" / "dummy").is_file()
    assert count_dir_contents(target_folder / "volumes" / "mounted") == 3
