import logging
import os
import sys
from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from compose import config as compose_config
from compose.config.errors import ConfigurationError

from dump import __version__
from dump.backup import create_dump
from dump.cli.utils import directory_exists
from dump.utils import setup_loghandler

COMPRESSIONS = ('bz2', 'gz',  'tar', 'xz')
COMPRESSION_EXTENSIONS = tuple('.' + x for x in COMPRESSIONS)
SCOPES = ('config', 'mounted', 'volumes')


log = logging.getLogger('compose-dump')

console_handler = logging.StreamHandler(sys.stderr)
log.addHandler(console_handler)

# Disable requests logging
logging.getLogger('requests').propagate = False


def parse_cli_args(args):
    parser = ArgumentParser(description='Backup and restore Docker-Compose projects.',
                            epilog='Restoring is not implemented yet.')
    parser.add_argument('--version', action='version', version=__version__)
    subparsers = parser.add_subparsers()
    add_backup_parser(subparsers)
    add_restore_parser(subparsers)
    return parser.parse_args(args)


def add_backup_parser(subparsers):
    desc, hlp = backup.__doc__.split('####\n')
    parser = subparsers.add_parser('backup', description=desc, help=hlp)
    parser.set_defaults(action=backup)
    parser.add_argument('--config', action='store_true', default=False,
                        help='Include configuration files, including referenced files '
                                'and build-contexts.')
    parser.add_argument('-x', '--compression', choices=COMPRESSIONS,
                        help='Sets the compression when an archive file is written. '
                                'Can also be provided as suffix on the target option.')
    parser.add_argument('-f', '--file', nargs='*', metavar='FILENAME',
                        help='Specifies alternate compose files.')
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
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='Log debug messages.')
    parser.add_argument('--volumes', action='store_true', default=False,
                        help='Include container volumes.')
    parser.add_argument('services', default=(), nargs='*', metavar='SERVICE...',
                        help='Restrict backup ob build contexts and volumes to these services.')


def add_restore_parser(parser):
    pass


def backup(args):
    """
    Backup a project and its data. Containers are not saved.

    If none of the include flags is provided, all are set to true.

    For example:

        $ compose-dump backup -t /var/backups/docker-compose
    ####
    """
    options = process_backup_options(vars(args).copy())
    config, config_details, environment = get_compose_context(options)
    log.debug('Invoking project dump with these settings: %s' % options)
    ctx = SimpleNamespace(
        options=options, manifest=OrderedDict(), config=config, config_details=config_details,
        environment=environment)
    create_dump(ctx)


def process_backup_options(options):
    del options['action']

    options['compose_files'] = options['file']
    del options['file']

    options['project_dir'] = Path(options['project_dir'])
    directory_exists(options['project_dir'])
    options['project_name'] = options['project_name'] or \
                              os.getenv('COMPOSE_PROJECT_NAME') or \
                              options['project_dir'].name

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
    try:
        config = compose_config.load(config_details)
    except ConfigurationError as e:
        log.error(e.msg)
        raise SystemExit(1)
    unknown_services = set(options['services']) - set(x['name'] for x in config.services)
    if unknown_services:
        log.error('Unknown services: %s' % ', '.join(unknown_services))
        raise SystemExit(1)
    if not options['services']:
        options['services'] = tuple(x['name'] for x in config.services)
    return config, config_details, environment


def main():
    # TODO unhandled exceptions
    args = parse_cli_args(sys.argv[1:])
    setup_loghandler(console_handler, args.verbose)
    args.action(args)

if __name__ == '__main__':
    main()
