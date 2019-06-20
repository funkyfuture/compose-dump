from pathlib import Path

from compose_dump.utils import PathSet


def test_pathset():
    ps = PathSet()

    x = "/ham"
    assert x not in ps
    ps.add(x)
    assert x in ps

    x = Path("/spam")
    assert x not in ps
    ps.add(x)
    assert x in ps
