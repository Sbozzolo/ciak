#!/usr/bin/env python3

# Copyright (C) 2021 Gabriele Bozzola
#
# This program is free software; you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this
# program; if not, see <https://www.gnu.org/licenses/>.

"""The :py:mod:`~.parser` module reads files and parse the content according to a syntax
based on asterisks. :py:mod:`~.parser` ignores all the lines that do not start with
asterisks (up to initial spaces), and reads the content as a tree with 'level' determined
by the number of asterisks. For example:

.. code-block

   # This is a comment
   ! This is a comment too
   * This is a first level item (1)
   ** This is a second level item (2)
   ** This is another second level item (3)
   *** This is a third level item (4)
   * This is another first level item (5)

This is represented as:

.. code-block

        (1)        (5)
       |   |
      (2) (3)
           |
          (4)

These will identify all the commands and arguments that ``ciak`` has to run.

The two main functions in the file are :py:func:`~.read_asterisk_lines_from_file`, which
reads to relevant lines from a file, and :py:func:`~.prepare_commands`, which takes the
output of the previous function to prepare a list of string that are going to be
executed.

"""

import re

# ^ matches the beginning of the line
# (\s)? matches any number of whitespaces
# (\*)+ matches one or more asterisk
# (\s)? matches any number of whitespaces
_ASTRISK_REGEX = r"^(\s)*(\*)+(\s)*"


def read_asterisk_lines_from_file(path: str) -> list[str]:
    """Read the file in ``path`` and read its content ignoring lines that do
    not start with asterisks (up to initial spaces).

    :param path: Path of the file to read.
    :type path: str
    :returns: List of strings with all the different lines that started with
              asterisk (up to the initial spaces).
    :rtype: list of str
    """

    # We read the entire file in one go. We are not expecting huge files, so this should
    # be okay.
    with open(path) as file_:
        lines = file_.read().splitlines()

    def start_with_asterisk(string: str):
        """Check if string starts with asterisks, up to initial spaces.

        :rtype: bool
        """
        rx = re.compile(_ASTRISK_REGEX)
        return rx.match(string) is not None

    return list(filter(start_with_asterisk, lines))


def prepare_commands(list_: list[str]) -> list[str]:
    """Transform a flat list of strings with asterisks into a list of full commands.

    This is done by walking through the tree and combining together those entries that
    are on the same branch. So

    .. code-block

        * One
        ** Two
        *** Three
        ** Four
        * Five

    will be turned into ``["One Two Three", "One Four", "Five"]``. This function is used
    in conjunction with :py:func:`~.read_asterisk_lines_from_file` to transform a
    configuration file into a list of commands to execute (including the whitespaces).

    :param list_: Output of :py:func:`~.read_asterisk_lines_from_file`
    :type list_: list of str
    :returns: List of commands.
    :rtype: list of str

    """
    # First we prepare another list with the number of asterisks of each element
    num_asterisks = list(map(lambda x: len(re.findall(r"\*", x)), list_))

    num_elements = len(num_asterisks)

    # Next, we remove all the asterisks and the whitespaces around them
    list_no_astr = list(map(lambda x: re.sub(_ASTRISK_REGEX, "", x), list_))

    return_list = []
    current_command = []
    for index, element in enumerate(list_no_astr):
        # Add the current element to the list current_command. We are going
        # to keep current_command updated.
        current_command.append(element)

        # Is this a leaf of the tree?
        # If this is the last element of the list, then it must be a leaf
        if index == num_elements - 1:
            return_list.append(" ".join(current_command))
            # There's no clean up to do here
        else:
            # Here it is not the last element of the list, so diff_levels is
            # well-defined
            diff_levels = num_asterisks[index + 1] - num_asterisks[index]
            # If diff_levels is negative, then it is a leaf because it means that the
            # next item as fewer asterisks
            if diff_levels <= 0:
                return_list.append(" ".join(current_command))
                # Now, current_command has to be synced to the correct level, which is
                # determined by diff_levels.
                #
                # For example, if we have
                # list_no_astr = ['1', '1.1', '1.1.1', '1.2', '2', '2.1']
                # and
                # num_asterisks = [1, 2, 3, 2, 1, 2]
                #
                # What have to happen is that at index = 2 we have to go back one level
                # because the following number of asterisks is 2 and we are we are
                # working with 3. Then, at index 3 we have to go back another level
                #
                # diff_levels is negative, so we overwrite current_command with
                # current_command excluding the last -abs(diff_levels) elements, as well
                # as the current one (-1)
                current_command = current_command[
                    : len(current_command) + diff_levels - 1
                ]

    return return_list
