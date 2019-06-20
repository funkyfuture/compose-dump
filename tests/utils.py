import os
import re
import sys
from hashlib import md5
from types import SimpleNamespace

from compose_dump import main


def count_dir_contents(path):
    return len(tuple(path.glob("*")))


def identical_files(file1, file2):
    return hash_file(file1).digest() == hash_file(file2).digest()


def identical_folder_contents(folder1, folder2, follow_symlinks=True):
    contents1 = set(x.name for x in folder1.glob("*"))
    contents2 = set(x.name for x in folder2.glob("*"))

    msg = ""
    if contents1 ^ contents2:
        missing_content = contents1 - contents2
        if missing_content:
            msg += "Missing contents in %s: %s" % (folder2, missing_content)

        extra_content = contents2 - contents1
        if extra_content:
            if msg:
                msg += "\n"
            msg += "Unexpected contents in %s: %s" % (folder2, extra_content)

        raise AssertionError(msg)

    for name in contents1:
        item1_path, item2_path = folder1 / name, folder2 / name
        if not follow_symlinks and item1_path.is_symlink():
            assert item2_path.is_symlink()
            assert os.readlink(str(item1_path)) == os.readlink(str(item2_path))
        elif item1_path.is_file():
            assert identical_files(item1_path, item2_path)
        elif item1_path.is_dir():
            identical_folder_contents(item1_path, item2_path)

    return True


def get_target_folder(target_folder):
    target_content = os.listdir(str(target_folder))
    assert len(target_content) == 1
    return target_folder / target_content[0]


def hash_file(file):
    result = md5()
    with file.open("rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            result.update(chunk)
    return result


def log_message(level, text_pattern, caplog):
    records = [x[1:] for x in caplog.record_tuples]
    for record in records:
        if record[0] == level and re.match(text_pattern, record[1]):
            break
    else:
        raise AssertionError(
            "Pattern %s at level %s not found in:\n%s" % (text_pattern, level, records)
        )
    return True


def result_okay(args):
    run_result = run(args)
    if run_result.exit_code != 0:
        raise AssertionError("Exit code: %s" % run_result.exit_code)
    return True


def run(args):
    args.insert(0, "compose-dump")
    args.insert(2, "--verbose")
    argv = sys.argv.copy()
    sys.argv = args
    try:
        main.main()
    except SystemExit as e:
        sys.argv = argv
        args.remove("compose-dump")
        args.remove("--verbose")
        result = SimpleNamespace()
        result.exit_code = e.code
        return result
    else:
        raise RuntimeError
