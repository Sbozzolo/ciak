#!/usr/bin/env python3

# Copyright (C) 2021 Gabriele Bozzola
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
