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


@pytest.mark.parametrize("argv", [["notes", "in.mid", "--track", "٣"], ["notes", "in.mid", "--track", "1_0"],
                                  ["feel", "in.mid", "--from", "r.mid", "-o", "o.mid", "--timing", "٥٠"]])
def test_a_number_flag_takes_ascii_digits_only(capsys, argv):
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert "in ASCII digits" in capsys.readouterr().err
