from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime
from io import StringIO
import logging
import os
from pathlib import Path, PurePath
from platform import node as gethostname
import sys

from compose.cli.command import get_config_path_from_options, get_project
from compose.config.config import ConfigFile
from compose.service import NoSuchImageError
try:
    from compose.version import ComposeVersion
except ImportError:
    from distutils.version import LooseVersion as ComposeVersion
import yaml

from compose_dump import VERSION
from compose_dump.utils import get_container_for_service, get_container_with_project_volume, hash_string, locates_in, \
    setup_loghandler, PathSet
from compose_dump.storage import init_storage


log = logging.getLogger('compose-compose_dump')


def dict_representer(dumper, data):
    return dumper.represent_dict(data.items())
yaml.add_representer(OrderedDict, dict_representer)  # noqa: E305


def create_dump(ctx):
    manifest_log = StringIO()
    manifest_handler = logging.StreamHandler(manifest_log)
    setup_loghandler(manifest_handler, ctx.options['verbose'])
    log.addHandler(manifest_handler)

    scopes = ctx.options['scopes']

    meta = ctx.manifest['meta'] = OrderedDict()
    meta['invocation_time'] = datetime.now().isoformat()
    meta['finish_time'] = None
    meta['argv'] = sys.argv
    meta['options'] = ctx.options
    meta['host'] = gethostname()
    meta['uid'] = os.getuid()
    meta['gid'] = os.getgid()
    meta['version'] = VERSION

    init_storage(ctx)

    base_dir = str(ctx.options['project_dir'])
    config_path = get_config_path_from_options(
        base_dir, {'--file': ctx.options['compose_files']}, ctx.environment)
    ctx.project = \
        get_project(base_dir, config_path=config_path,
                    project_name=ctx.options['project_name'],
                    verbose=ctx.options['verbose'], host=None, tls_config=None, environment=ctx.environment)

    if 'config' in scopes:
        store_config(ctx)

    if 'mounted' in scopes or 'volumes' in scopes:
        if not ctx.options['no_pause']:
            ctx.project.pause(service_names=ctx.options['services'])
        store_volumes(ctx)
        if not ctx.options['no_pause']:
            ctx.project.unpause(service_names=ctx.options['services'])

    meta['finish_time'] = datetime.now().isoformat()

    normalize_manifest_mapping(ctx.manifest)
    manifest_log.seek(0)

    doc = yaml.dump(ctx.manifest, default_flow_style=False)
    doc += '---\n'
    doc += yaml.dump([x.strip() for x in manifest_log.readlines() if x], default_style='"')

    ctx.storage.write_file(doc, 'Manifest.yml')

    ctx.storage.finalize()


####


def normalize_manifest_mapping(mapping):
    for key, value in mapping.items():
        mapping[key] = normalize_manifest_value(value)


def normalize_manifest_sequence(sequence):
    result = []
    for item in sequence:
        result.append(normalize_manifest_value(item))
    return result


def normalize_manifest_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Sequence):
        return normalize_manifest_sequence(value)
    if isinstance(value, Mapping):
        normalize_manifest_mapping(value)
    return value


####


def store_config(ctx):
    considered_files = PathSet()
    for compose_file in ctx.config_details.config_files:
        store_config_file(ctx, compose_file, considered_files)

    store_build_contexts(ctx)

    env_file = ctx.options['project_dir'] / '.env'
    if env_file.exists():
        put_config_file(ctx, env_file, considered_files)


def store_config_file(ctx, compose_file, considered_files):
    filepath = Path(compose_file.filename)
    fileparent = filepath.parent
    compose_file_version = compose_file.version
    if not isinstance(compose_file_version, ComposeVersion):  # up to Docker-Compose 1.14
        compose_file_version = ComposeVersion(compose_file_version)

    put_config_file(ctx, filepath, considered_files)

    if compose_file_version < ComposeVersion('2'):
        services = compose_file.config
    elif compose_file_version < ComposeVersion('4'):
        services = compose_file.config['services']
    else:
        log.error('Unsupported config version: %s' % compose_file.version)
        raise SystemExit(1)

    for service in services.values():
        env_files = service.get('env_file', ())
        if isinstance(env_files, str):
            env_files = (env_files,)
        for env_file in env_files:
            env_file_path = fileparent / env_file
            put_config_file(ctx, env_file_path, considered_files)

        extends_file = service.get('extends', {}).get('file')
        if extends_file is None:
            continue

        extends_file_path = fileparent / extends_file
        extends_file = ConfigFile.from_filename(str(extends_file_path))
        store_config_file(ctx, extends_file, considered_files)


def put_config_file(ctx, filepath, considered_files):
    if filepath in considered_files:
        return

    project_dir = ctx.options['project_dir']
    dst = filepath.parent.relative_to(project_dir)

    if filepath.is_symlink() and not ctx.options['resolve_symlinks']:
        if locates_in(filepath, project_dir):
            ctx.storage.put_file(filepath, dst, namespace='config', follow_symlinks=False)
        considered_files.add(filepath)
        filepath = filepath.resolve()

    if filepath in considered_files:
        return

    if locates_in(filepath, project_dir):
        ctx.storage.put_file(filepath, dst, namespace='config')
    considered_files.add(filepath)


def store_build_contexts(ctx):
    project_dir = ctx.options['project_dir']
    # create set of paths to copy to avoid duplicated copies
    config_dirs = set()

    for service in ctx.project.services:
        if service.name not in ctx.options['services']:
            continue
        build_options = service.options.get('build')
        if not build_options:
            continue

        context = build_options.get('context')
        if context:
            dst = Path(context).relative_to(project_dir)
            config_dirs.add((project_dir / context, dst))

    for config_dir in config_dirs:
        ctx.storage.put_folder(config_dir[0], config_dir[1], namespace='config')


####


def store_volumes(ctx):
    volume_index = ctx.manifest['volumes'] = OrderedDict()
    volume_index['project'] = {}
    volume_index['mounted'] = []
    volume_index['services'] = {}
    mounted_paths = PathSet()

    if 'volumes' in ctx.options['scopes']:
        store_project_volumes(ctx)
    store_services_volumes(ctx, mounted_paths)
    if 'mounted' in ctx.options['scopes']:
        store_mounted_volumes(ctx, mounted_paths)


def store_project_volumes(ctx):
    for name, volume in ctx.project.volumes.volumes.items():
        if volume.external:
            continue
        if not volume.exists():
            log.critical("Project volume %s doesn't exist." % name)
            continue
        else:
            container, path = get_container_with_project_volume(ctx.project, name)
            if container is None:
                log.critical('Found no container that uses project volume %s' % name)
                continue
            bits, stat = ctx.project.client.get_archive(container.id, path)
            archive_name = name + '.tar'
            if hasattr(bits, 'stream'):  # TODO: obsolete with docker-compose>1.19.0 (e.g. docker-py>=3.0.0)
                bits = bits.stream
            ctx.storage.write_file(bits, archive_name, namespace='volumes/project')
            ctx.manifest['volumes']['project'][name] = archive_name


def store_services_volumes(ctx, mounted_paths):
    for service in ctx.project.services:
        if service.name not in ctx.options['services']:
            continue

        internal_volumes = PathSet()
        considered_paths = PathSet()

        # figure out what should be saved
        for volume in service.options.get('volumes', ()):
            if volume.external in ctx.project.volumes.volumes:
                pass
            elif volume.external is None:
                internal_volumes.add(volume.internal)
            elif locates_in(volume.external, ctx.options['project_dir']):
                mounted_paths.add(volume.external)
            considered_paths.add(volume.internal)

        # collect extra volumes from service image
        try:
            image = service.image()
        except NoSuchImageError as e:
            log.critical('%s: %s' % (service.name, e))
        else:
            image_volumes = image.get('Config', {})['Volumes'] or ()
            for volume in image_volumes:
                if volume not in considered_paths:  # not if encountered before
                    internal_volumes.add(volume)

        if 'volumes' in ctx.options['scopes']:
            index = ctx.manifest['volumes']['services'][service.name] = {}
            container = get_container_for_service(service)
            if container is None:
                log.critical('No container for service %s found.' % service.name)
                continue
            for path in internal_volumes:
                archive_name = hash_string(service.name.upper() + path) + '.tar'
                bits, stat = ctx.project.client.get_archive(container.id, path)
                if hasattr(bits, 'stream'):  # TODO: obsolete with docker-compose>1.19.0 (e.g. docker-py>=3.0.0)
                    bits = bits.stream
                ctx.storage.write_file(bits, archive_name, namespace='volumes/services')
                index[path] = archive_name


def store_mounted_volumes(ctx, mounted_paths):
    for path in mounted_paths:
        path = Path(path)
        dst = path.relative_to(ctx.options['project_dir'])
        if path.is_dir():
            ctx.storage.put_folder(path, dst, namespace='volumes/mounted')
        else:
            ctx.storage.put_file(path, dst.parent, namespace='volumes/mounted')
        ctx.manifest['volumes']['mounted'].append(dst)
