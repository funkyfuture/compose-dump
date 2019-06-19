Overview
========

::

    This piece of code is tested with only a small number of use-cases yet.
    You are invited to contribute.


``compose-dump`` let's you backup and (not yet) restore `Docker Compose`_
-projects. Like ``docker-compose`` this tool operates usually in a project-
folder. It's intended to be a simple tool for usage within a broader
backup-logic. The extent of a backup can be controlled by content scopes and
services.

Main features
-------------

- Archives Docker Compose projects.
- Optionally include configuration with all its referenced files.
- Optionally include volumes of specified services.
- Store dumps in a directory, as archive on disk or as archive to the standard
  output.


See planned features below.

Installation
------------

With `pipx`_ (recommended to avoid library version conflicts), also installs
Docker-Compose::

    $ pipx install compose-dump

Or with `pip`_, installs Docker-Compose when not already present in the installation
context::

    $ pip install compose-dump

The package is managed with poetry_. To install it in editable_ mode, including
Docker-Compose::

    …/compose-dump $ poetry install


Usage
-----

Examples
~~~~~~~~

Fully dump a compose-project from ``project_path`` to ``/var/backups/compose``::

    $ cd project_path
    $ compose-dump backup -t /var/backups/compose

Write a gzip-compressed archive to a remote host via ssh::

    $ cd project_path
    $ compose-dump backup -x gz | ssh user@host "cat - > ~/backup.tar.gz"

Only dump configuration and data from container-volumes of the service ``web``::

    $ compose-dump backup --config --volumes web

Backup all projects with a ``docker-compose.yml`` to ``/var/backups/compose``::

    $ find . -name "docker-compose.yml" -type f -execdir compose-dump backup -t /var/backups/compose \;

Command line reference::

    $ compose-dump
    $ compose-dump backup --help

Backup structure
~~~~~~~~~~~~~~~~

Any data that is located outside the project's scope is ignored. In
particular this are mounted volumes that are not in the project-path or below
and volumes in ``volumes_from``-referenced containers. Consider this not as
a limitation, but as a feature to endorse good practices; handle these
objects in your broader backup-logic.

The resulting dump is structured this way:

::

    + <hostname>_<project_name>__<shorted_path_hash>___<date>_<time>  # that's the default
      - Manifest.yml
      + config
        - <config_files>…  # Usually docker-compose.yml and its referenced files
        - <build_contexts>…
      + volumes
        + mounted
          <host path relative to project path>…
        + project
          <project volume in a tar archive>…
        + services
          + <service>…
            <service volume in a tar archive>…

Contributing
------------

Fork it, report issues and open pull requests at
https://github.com/funkyfuture/compose-dump .

Testing
~~~~~~~

The integration tests require a docker client on the test machine. To
keep the temporary directories that contain integration tests' results,
invoke ``pytest`` with the ``--keep-results`` option.

Before opening a pull request, make sure you run tests against all supported
dependencies with ``make test-all``.

You are free to hate me for relying mainly on integration tests. But
keep it to yourself, the world's already filled up with hatred. I
suggest anyone with such sentiment uses this dark energy to implement
improvements.

Style notes
~~~~~~~~~~~

The code may seem cumbersome when it comes to paths. This is caused by
anticipation of the `file system path protocol`_ that comes with
Python 3.6 and later. The rule of thumb here is: Always use
:class:`pathlib.Path` objects to represent paths, convert values for function
calls with :func:`str`, convert results to ``Path`` instances. Until 3.6's
reign has come.

TODO / Known issues / Caveats
-----------------------------

general
~~~~~~~

- make use of compose config hashes
- docs: point to environment variables regarding tls config
- make use of mypy

backup
~~~~~~

You may run into issues if a volume's archive delivered by the Docker daemon
is larger than the available memory. Thus you should avoid such scenarios on
production systems. This does not apply for mounted volumes. If you can't
avoid such cases, please open an issue.

- test volumes defined in extended services
- filter volumes
- only pause actually affected services
- backup-configuration from a file in a project's folder
- maybe:

  - respect .dockerignore
  - .backupignore
  - read config from stdin

restore
~~~~~~~

-  implement an automated restoration of a project-dump
-  read from stdin


.. _`Docker Compose`: https://docs.docker.com/compose/
.. _editable: https://packaging.python.org/guides/distributing-packages-using-setuptools/#working-in-development-mode
.. _`file system path protocol`: https://www.python.org/dev/peps/pep-0519/
.. _`pip`: https://packaging.python.org/installing/#use-pip-for-installing
.. _`pipx`: https://pipxproject.github.io/pipx/
.. _poetry: https://poetry.eustace.io/docs/
