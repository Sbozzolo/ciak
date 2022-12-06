#!/usr/bin/env python3

# Copyright (C) 2021-2022 Gabriele Bozzola
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <https://www.gnu.org/licenses/>.

import os
from unittest import mock

import pytest

from ciak import ciak


def test_read_asterisk_lines_from_file():

    expected_output = (
        "* Item 1",
        "** Item 1.1",
        "*** Item 1.1.1",
        "*Item 2",
        " * Item 3",
    )

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "example_file.txt")

    assert ciak.read_asterisk_lines_from_file(path) == expected_output


def test_extract_execution_blocks():

    # No PARELLEL_END
    with pytest.raises(RuntimeError):
        ciak.extract_execution_blocks(("* # BEGIN_PARALLEL",))

    # PARELLEL_END without PARALLEL_BEGIN
    with pytest.raises(RuntimeError):
        ciak.extract_execution_blocks(("* # END_PARALLEL",))

    # Empty parallel block
    with pytest.warns(Warning):
        ciak.extract_execution_blocks(("* # BEGIN_PARALLEL", "* # END_PARALLEL"))

    input_ = (
        "* ls",
        "** -la",
        "* # BEGIN_PARALLEL",
        "* touch this",
        "* touch this_too",
        "* # END_PARALLEL",
        "* touch that",
    )

    expected_out = (
        ciak.ExecutionBlock(("ls -la",), False),
        ciak.ExecutionBlock(("touch this", "touch this_too"), True),
        ciak.ExecutionBlock(("touch that",), False),
    )

    assert ciak.extract_execution_blocks(input_) == expected_out


def test_prepare_commands():

    # This is a fairly rich list with multiple cases
    list_ = (
        "* 1",
        " ** 1.1",
        "*** 1.1.1",
        "*** 1.1.2",
        "** 1.2",
        "* 2",
        "** 2.1",
        "*** 2.1.1",
        "*** 2.1.2",
        "* 3",
        "* 4",
    )
    expected_output = (
        "1 1.1 1.1.1",
        "1 1.1 1.1.2",
        "1 1.2",
        "2 2.1 2.1.1",
        "2 2.1 2.1.2",
        "3",
        "4",
    )

    assert ciak.prepare_commands(list_) == expected_output


def test_substitute_template():

    # Nothing to do
    assert ciak.substitute_template("test", {}) == "test"

    # Nothing to do
    assert ciak.substitute_template("test", {"bob": "unaga"}) == "test"
    # One sub
    assert ciak.substitute_template("{{test}}", {"test": "bob"}) == "bob"

    # One sub with default not used
    assert ciak.substitute_template("{{test::lol}}", {"test": "bob"}) == "bob"

    # One sub with default used
    assert ciak.substitute_template("{{test::lol}}", {"mamma": "gamma"}) == "lol"

    # One sub without the default and missing key
    with pytest.raises(RuntimeError):
        ciak.substitute_template("{{test}}", {"mytest": "bob"})

    # Two subs
    assert (
        ciak.substitute_template(
            "{{test1}} and {{test2}}", {"test1": "mamma", "test2": "gamma"}
        )
        == "mamma and gamma"
    )

    # Two subs one with default not used
    assert (
        ciak.substitute_template(
            "{{test1}} and {{test2::lol}}", {"test1": "mamma", "test2": "gamma"}
        )
        == "mamma and gamma"
    )

    # Two subs one with default
    assert (
        ciak.substitute_template(
            "{{test1}} and {{test2::lol}}", {"test1": "mamma", "LOL": "gamma"}
        )
        == "mamma and lol"
    )


def test_get_ciakfile(tmp_path):

    # Not passing anything (passing None, None)
    with pytest.raises(RuntimeError):
        assert ciak.get_ciakfile(None, None)

    # Passing the ciakfile_path (we have to ensure that the file exists)
    path = tmp_path / "myciak.org"
    path.write_text("* echo 'hi'")

    assert ciak.get_ciakfile("anything", str(path)) == str(path)

    # Passing the ciakfile and 'CIAKFILES_DIR'
    with mock.patch.dict(os.environ, {"CIAKFILES_DIR": str(tmp_path / "")}):
        assert ciak.get_ciakfile("myciak.org", None) == str(path)

    # Passing the ciakfile but not 'CIAKFILES_DIR', so we should use the current
    # directory. To keep things clean, instead, we change our directory
    os.chdir(str(tmp_path / ""))
    assert ciak.get_ciakfile("myciak.org", None) == str(path)

    # ciakfile not existing
    with pytest.raises(RuntimeError):
        assert ciak.get_ciakfile("ciok.bob", None)


def test_run_one_command():
    # _run_command takes a string for the command and returns the exit code
    assert ciak._run_one_command("ls -l -a -h") == 0


def test_run_commands():

    # Test two commands sequentially, just checking that there are no errors
    _ = ciak.run_commands(("ls -l -a -h", "ls -h -a"))

    # Check with fail_fast (we trigger an error by providing a folder that does
    # not exist)
    _ = ciak.run_commands(("ls bobby", "ls -h -a"), fail_fast=True)

    # Test two commands in parallel, just checking that there are no errors
    _ = ciak.run_commands(("ls -l -a -h", "ls -h -a"), parallel=True)


def test_main(tmp_path):
    # Integration test
    #
    # We check a fairly complete case with parallel execution and substitutions
    #

    path = tmp_path / "ciak_integration.org"

    path.write_text(
        """\
* mkdir {{where::/tmp}}/{{subdir::sub}}
* # BEGIN_PARALLEL
* touch
** {{where::/tmp}}/{{subdir::sub}}/this
** {{where::/tmp}}/{{subdir::sub}}/that
* # END_PARALLEL"""
    )

    with mock.patch(
        "sys.argv",
        [
            "main",
            "--ciakfile-path",
            str(path),
            "--where",
            str(tmp_path / ""),
            "--verbose",
        ],
    ):
        ciak.main()

    assert os.path.isfile(tmp_path / "sub/this") is True

    with mock.patch(
        "sys.argv",
        [
            "main",
            "--ciakfile-path",
            str(path),
            "--where",
            str(tmp_path / ""),
            "--verbose",
        ],
    ):
        ciak.main()
