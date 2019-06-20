import logging
from collections.abc import Set
from hashlib import sha256
import os


class PathSet(Set):
    def __init__(self, iterable=()):
        self.items = set()
        for item in iterable:
            self.add(item)

    def __contains__(self, item):
        return self._norm_value(item) in self.items

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def _norm_value(self, value):
        return normpath(str(value))

    def add(self, value):
        self.items.add(self._norm_value(value))


def get_container_with_project_volume(project, volume_name):
    volume_name = "%s_%s" % (project.name, volume_name)
    for service in project.services:
        for volume in service.options.get("volumes", ()):
            if volume.external == volume_name:
                container = get_container_for_service(service)
                if container:
                    return container, volume.internal
    return None, None


def get_container_for_service(service):
    containers = service.containers(stopped=True) or service.containers(
        stopped=True, one_off=True
    )
    if containers:
        return containers[0]
    else:
        return None


def hash_string(value, length=8):
    return sha256(str(value).encode()).hexdigest()[:length]


def locates_in(path, directory):
    path = normpath(path)
    directory = normpath(directory)
    return path.startswith(directory + os.sep)


def normpath(path):
    return os.path.normpath(str(path))


def setup_loghandler(handler, verbose=False):
    log_level = logging.DEBUG if verbose else logging.INFO
    handler.setFormatter(
        logging.Formatter("{asctime}::{levelname}::{message}", style="{")
    )
    handler.setLevel(log_level)
