import logging

from pytest import mark

from compose_dump.main import get_compose_context
from tests.utils import log_message, run


@mark.usefixtures("project_dir")
def test_nested_extends(caplog):
    result = run(["backup", "spam"])
    assert result.exit_code == 1
    assert log_message(logging.ERROR, "Unknown services: spam", caplog)
    caplog.clear()


def test_two_compose_files(project_dir):
    options = {
        "project_dir": project_dir,
        "compose_files": ("ham.yml", "spam.yml"),
        "services": (),
    }
    config, _, _ = get_compose_context(options)
    services = [x["name"] for x in config.services]
    assert "ham" in services
    assert "spam" in services
