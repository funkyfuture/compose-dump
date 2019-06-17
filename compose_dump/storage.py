import abc
from functools import wraps
import io
import logging
import os
from pathlib import Path
import shutil
import sys
import tarfile
import types
from time import time

from compose_dump.utils import hash_string

log = logging.getLogger('compose-compose_dump')


def copy(src, dst, *args, **kwargs):
    shutil.copy2(str(src), str(dst), *args, **kwargs)


def copytree(src, dst, *args, **kwargs):
    shutil.copytree(str(src), str(dst), *args, **kwargs)


def ensure_path_type(method):
    @wraps(method)
    def wrapper(self, src, dst, **kwargs):
        if not isinstance(src, Path):
            src = Path(src)
        if not isinstance(dst, Path):
            dst = Path(dst)
        method(self, src, dst, **kwargs)
    return wrapper


def expand_dst(method):
    @wraps(method)
    def wrapper(self, src, dst, **kwargs):
        namespace = kwargs.get('namespace', '.')
        ancestors = self.root_path
        for part in namespace.split('/'):
            ancestors /= part
        method(self, src, ancestors / dst, **kwargs)
    return wrapper


class StorageAdapterBase(abc.ABC):
    @staticmethod
    def _make_name(ctx):
        isodate = ctx.manifest['meta']['invocation_time']
        return ctx.options['target_pattern'].format(
            date=isodate[:10],
            isodate=isodate,
            host=ctx.manifest['meta']['host'],
            name=ctx.options['project_name'],
            path_hash=hash_string(ctx.options['project_dir']),
            time=isodate[11:16]
        )

    def finalize(self):
        pass

    @abc.abstractmethod
    def put_file(self, src, dst, namespace='.', follow_symlinks=True):
        pass

    @abc.abstractmethod
    def put_folder(self, src, dst, namespace='.'):
        pass

    @abc.abstractmethod
    def write_file(self, dst, data, namespace='.'):
        pass


class ArchiveStorage(StorageAdapterBase):
    def __init__(self, ctx):
        target = ctx.options['target']
        compression = ctx.options['compression']
        if target is None:
            mode = 'w|'
            fileobj = sys.stdout.buffer
        else:
            mode = 'w:'
            fileobj = None
            if target.is_dir():
                name = self._make_name(ctx) + '.tar'
                if compression != 'tar':
                    name += '.' + compression
                target /= name
            target = str(target)
        if compression != 'tar':
            mode += compression

        self.archive = tarfile.open(target, mode, fileobj)
        self.root_path = Path('.')

    def finalize(self):
        self.archive.close()

    @ensure_path_type
    @expand_dst
    def put_file(self, src, dst, namespace='.', follow_symlinks=True):
        dst /= src.name
        if follow_symlinks:
            src = src.resolve()
        self.archive.add(str(src), str(dst))

    @expand_dst
    def put_folder(self, src, dst, namespace='.'):
        self.archive.add(str(src), str(dst))

    @expand_dst
    def write_file(self, data, dst, namespace='.'):
        if isinstance(data, str):
            data = data.encode()
        if isinstance(data, bytes):
            size = len(data)
            buffer = io.BytesIO(data)
        elif callable(data):  # TODO: obsolete with docker-compose>1.19.0 (e.g. docker-py>=3.0.0)
            size = 0
            buffer = io.BytesIO()
            for chunk in data():
                size += len(chunk)
                buffer.write(chunk)
            buffer.seek(0)
        elif isinstance(data, types.GeneratorType):
            size = 0
            buffer = io.BytesIO()
            for chunk in data:
                size += len(chunk)
                buffer.write(chunk)
            buffer.seek(0)

        tarinfo = tarfile.TarInfo(str(dst))
        tarinfo.size = size
        tarinfo.mtime = time()
        tarinfo.mode = 440
        tarinfo.uid = os.getuid()
        tarinfo.gid = os.getgid()
        self.archive.addfile(tarinfo, buffer)


class FolderStorage(StorageAdapterBase):
    def __init__(self, ctx):
        self.target_path = ctx.options['target']
        if self.target_path.exists():
            self.target_path /= self._make_name(ctx)
            self.target_path.mkdir()
        self.root_path = self.target_path

    @ensure_path_type
    @expand_dst
    def put_file(self, src, dst, namespace='.', follow_symlinks=True):
        if not dst.exists():
            dst.mkdir(parents=True)

        copy(src, dst, follow_symlinks=follow_symlinks)

    @ensure_path_type
    @expand_dst
    def put_folder(self, src, dst, namespace='.'):
        if not dst.parent.exists():
            dst.parent.mkdir(parents=True)
        copytree(src, dst)

    @expand_dst
    def write_file(self, data, dst, namespace='.'):
        if not dst.parent.exists():
            dst.parent.mkdir(parents=True)
        if isinstance(data, str):
            with dst.open('wt') as f:
                print(data, file=f)
        elif isinstance(data, bytes):
            with dst.open('wb') as f:
                f.write(data)
        elif callable(data):  # TODO: obsolete with docker-compose>1.19.0 (e.g. docker-py>=3.0.0)
            with dst.open('wb') as f:
                for chunk in data():
                    f.write(chunk)
        elif isinstance(data, types.GeneratorType):
            with dst.open('wb') as f:
                for chunk in data:
                    f.write(chunk)


def init_storage(ctx):
    if ctx.options['target_type'] == 'archive':
        ctx.storage = ArchiveStorage(ctx)
    elif ctx.options['target_type'] == 'folder':
        ctx.storage = FolderStorage(ctx)
