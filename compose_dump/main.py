import logging
import os
import sys
from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from compose import config as compose_config

from compose_dump import VERSION
from compose_dump.backup import create_dump
from compose_dump.utils import setup_loghandler

COMPRESSIONS = ('bz2', 'gz',  'tar', 'xz')
COMPRESSION_EXTENSIONS = tuple('.' + x for x in COMPRESSIONS)
SCOPES = ('config', 'mounted', 'volumes')


####


log = logging.getLogger('compose-compose_dump')

console_handler = logging.StreamHandler(sys.stderr)
log.addHandler(console_handler)

# Disable requests logging
logging.getLogger('requests').propagate = False


####


def directory_exists(path):
    if not path.exists():
        log.error('%s does not exist.' % path)
        raise SystemExit(1)
    if not path.is_dir():
        log.error('%s is not a directory' % path)
        raise SystemExit(1)


####


def parse_cli_args(args):
    parser = ArgumentParser()
    parser.add_argument('--version', action='version', version=VERSION)
    subparsers = parser.add_subparsers()
    add_backup_parser(subparsers)
    add_restore_parser(subparsers)
    args = parser.parse_args(args)
    if not hasattr(args, 'action'):
        args.action = help
    return args


def add_backup_parser(subparsers):
    desc, hlp = backup.__doc__.split('####\n')
    parser = subparsers.add_parser('backup', description=desc.strip(), help=hlp.strip())
    parser.set_defaults(action=backup)
    parser.add_argument('--config', action='store_true', default=False,
                        help='Include configuration files, including referenced files '
                             'and build-contexts.')
    parser.add_argument('-x', '--compression', choices=COMPRESSIONS,
                        help='Sets the compression when an archive file is written. '
                             'Can also be provided as file extension on the --target option.')
    parser.add_argument('-f', '--file', nargs='*', metavar='FILENAME',
                        help='Specifies compose files.')
    parser.add_argument('--mounted', action='store_true', default=False,
                        help='Include mounted volumes, skips paths outside project folder.')
    parser.add_argument('--no-pause', action='store_true', default=False,
                        help="Don't pause containers during backup")
    parser.add_argument('--project-dir', default=os.getcwd(), metavar='PATH',
                        help="Specifies the project's root folder, defaults to the current "
                             "directory.")
    parser.add_argument('-p', '--project-name', help='Specifies an alternate project name.')
    parser.add_argument('--resolve-symlinks', action='store_true', default=False,
                        help='References to configuration files that are symlinks are stored as '
                             'files.')
    parser.add_argument('--target', '-t', metavar='PATH', help='Dump target, defaults to stdout.')
    parser.add_argument('--target-pattern', metavar='PATTERN', default='{host}__{name}__{path_hash}_{date}_{time}',
                        help='String template for the backup name. May include the placeholders {date}, {host},'
                             '{isodate}, {name}, {path_hash} and {time}.')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='Log debug messages.')
    parser.add_argument('--volumes', action='store_true', default=False,
                        help='Include container volumes.')
    parser.add_argument('services', default=(), nargs='*', metavar='SERVICE',
                        help='Restrict backup of build contexts and volumes to these services.')


def add_restore_parser(parser):
    pass


####


def help(args):
    print("""Backup and restore Docker-Compose projects.

Use one of the subcommands `backup` or `restore`.
For help on each append the `--help` argument.

Restoring is not implemented yet.

Online documentation: http://compose-dump.rtfd.io/
""")

####


def backup(args):
    """
    Backup a project and its data. Containers are not saved.

    If none of the include flags is provided, all are set to true.

    For example:

        $ compose-compose_dump backup -t /var/backups/docker-compose
    ####
    """
    options = process_backup_options(vars(args).copy())
    config, config_details, environment = get_compose_context(options)
    log.debug('Invoking project compose_dump with these settings: %s' % options)
    ctx = SimpleNamespace(
        options=options, manifest=OrderedDict(), config=config, config_details=config_details,
        environment=environment)
    create_dump(ctx)


def process_backup_options(options):
    del options['action']

    options['compose_files'] = options['file']
    del options['file']

    options['project_dir'] = Path(options['project_dir']).resolve()
    directory_exists(options['project_dir'])
    options['project_name'] = (options['project_name'] or
                               os.getenv('COMPOSE_PROJECT_NAME') or
                               options['project_dir'].name)

    options['scopes'] = ()
    for scope in SCOPES:
        if options[scope]:
            options['scopes'] += (scope,)
        del options[scope]
    if not options['scopes']:
        options['scopes'] = SCOPES

    if options['target'] is not None:
        options['target'] = Path(options['target'])
        if options['compression'] is None and \
                options['target'].suffix in COMPRESSION_EXTENSIONS:
            options['compression'] = options['target'].suffix[1:]
    elif options['compression'] is None:
        options['compression'] = 'tar'
    if options['compression']:
        options['target_type'] = 'archive'
    else:
        directory_exists(options['target'])
        options['target_type'] = 'folder'

    return options


def get_compose_context(options):
    base_dir = str(options['project_dir'])
    environment = compose_config.environment.Environment.from_env_file(base_dir)
    config_details = compose_config.find(base_dir, options['compose_files'], environment)
    config = compose_config.load(config_details)
    unknown_services = set(options['services']) - set(x['name'] for x in config.services)
    if unknown_services:
        log.error('Unknown services: %s' % ', '.join(unknown_services))
        raise SystemExit(1)
    if not options['services']:
        options['services'] = tuple(x['name'] for x in config.services)
    return config, config_details, environment


####


def main():
    try:
        args = parse_cli_args(sys.argv[1:])
        setup_loghandler(console_handler, getattr(args, 'verbose', False))
        log.setLevel(console_handler.level)
        args.action(args)
    except SystemExit as e:
        exit_code = e.code
    except compose_config.ConfigurationError as e:
        log.error(e.msg)
        exit_code = 1
    except Exception as e:
        log.error('An unhandled exception occurred, please submit a bug report:')
        log.exception(e)
        exit_code = 3
    else:
        exit_code = 0

    raise SystemExit(exit_code)
