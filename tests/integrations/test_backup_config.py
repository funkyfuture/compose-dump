import logging
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from pytest import mark
import yaml

from tests.utils import log_message, get_target_folder, identical_folder_contents, result_okay, run


@mark.parametrize('compression', ('', 'tar', 'gz', 'bz2', 'xz'))
@mark.parametrize('resolve_symlinks', (True, False))
@mark.parametrize('target', (True, False))
def test_yet_another_blog(project_dir, temp_dir, target, compression, resolve_symlinks):
    args = ['backup']

    if target:
        args.extend(['-t', str(temp_dir)])
    if compression:
        args.extend(['--compression', compression])
    if resolve_symlinks:
        args.append('--resolve-symlinks')

    assert result_okay(args)

    if target:
        target_item = get_target_folder(temp_dir)
    else:
        return  # FIXME https://github.com/pytest-dev/pytest/issues/1407
        out, err = capsys.readouterr()  # noqa: F821
        target_item = temp_dir / 'archive'
        with target_item.open('wb') as f:
            f.write(out)

    if compression:
        assert target_item.is_file()
        with TemporaryDirectory() as tmp:
            archive = tarfile.open(str(target_item))
            archive.extractall(tmp)
            assert identical_folder_contents(project_dir, Path(tmp) / 'config', resolve_symlinks)
    else:
        assert target_item.is_dir()
        target_folder = target_item
        assert identical_folder_contents(project_dir, target_folder / 'config', resolve_symlinks)


def test_config_with_build_context_v1(project_dir, temp_dir):
    assert result_okay(['backup', '-t', str(temp_dir)])
    target_folder = get_target_folder(temp_dir)
    assert identical_folder_contents(project_dir, target_folder / 'config')


def test_config_with_build_context_v2(project_dir, temp_dir):
    assert result_okay(['backup', '-t', str(temp_dir)])
    target_folder = get_target_folder(temp_dir)
    assert identical_folder_contents(project_dir, target_folder / 'config')


def test_config_with_duplicated_build_context(project_dir, temp_dir):
    assert result_okay(['backup', '-t', str(temp_dir)])
    target_folder = get_target_folder(temp_dir)
    assert identical_folder_contents(project_dir, target_folder / 'config')


@mark.parametrize('resolve_symlinks', (True, False))
def test_nested_extends(project_dir, temp_dir, resolve_symlinks):
    args = ['backup', '-t', str(temp_dir)]
    if resolve_symlinks:
        args.append('--resolve-symlinks')

    assert result_okay(args)
    target_folder = get_target_folder(temp_dir)
    assert identical_folder_contents(project_dir, target_folder / 'config')


@mark.parametrize('resolve_symlinks', (True, False))
def test_missing_files(project_dir, temp_dir, resolve_symlinks, caplog):
    args = ['backup', '-t', str(temp_dir)]
    if resolve_symlinks:
        args.append('--resolve-symlinks')

    result = run(args)
    assert result.exit_code == 1
    assert log_message(logging.ERROR, r'\.FileNotFoundError:', caplog)

    extends_content = {'version': '2', 'services': {'none': {'image': 'busybox'}}}
    with project_dir.add_file('void.yml').open('tw') as f:
        yaml.dump(extends_content, f)
    caplog.clear()
    result = run(args)

    assert result.exit_code == 1
    assert log_message(logging.ERROR, r'build path .*/lost either does not exist', caplog)

    project_dir.add_folder('lost')
    caplog.clear()
    result = run(args)
    assert result.exit_code == 1
    assert log_message(logging.ERROR, r"Couldn't find env file: .*/dangling_link$", caplog)

    project_dir.add_file('gone')
    caplog.clear()
    assert result_okay(args)
