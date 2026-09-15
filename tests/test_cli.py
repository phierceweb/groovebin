import pytest

from groovebin import __version__
from groovebin.cli import main


def test_version_names_the_package(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"groovebin {__version__}"


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage: groovebin" in capsys.readouterr().out
