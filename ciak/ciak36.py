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

# THIS IS A TEMPORARY SOLUTION TO PROVIDE SUPPORT FOR PYTHON3.6

import argparse
import logging
import subprocess
import re

LOGGER = logging.getLogger(__name__)

# ^ matches the beginning of the line
# (\s)? matches any number of whitespaces
# (\*)+ matches one or more asterisk
# (\s)? matches any number of whitespaces
_ASTRISK_REGEX = r"^(\s)*(\*)+(\s)*"


def read_asterisk_lines_from_file(path):
    """Read the file in ``path`` and read its content ignoring lines that do
    not start with asterisks (up to initial spaces).

    :param path: Path of the file to read.
    :type path: str
    :returns: List of strings with all the different lines that started with
              asterisk (up to the initial spaces).
    :rtype: tuple of str
    """

    # We read the entire file in one go. We are not expecting huge files, so this should
    # be okay.
    with open(path) as file_:
        lines = file_.read().splitlines()

    for line in lines:
        LOGGER.debug(line)

    def start_with_asterisk(string: str):
        """Check if string starts with asterisks, up to initial spaces.

        :rtype: bool
        """
        rx = re.compile(_ASTRISK_REGEX)
        return rx.match(string) is not None

    return tuple(filter(start_with_asterisk, lines))


def prepare_commands(list_):
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
    :rtype: tuple of str

    """
    # First we prepare another list with the number of asterisks of each element
    num_asterisks = tuple(map(lambda x: len(re.findall(r"\*", x)), list_))

    num_elements = len(num_asterisks)

    # Next, we remove all the asterisks and the whitespaces around them
    list_no_astr = tuple(map(lambda x: re.sub(_ASTRISK_REGEX, "", x), list_))

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

    return tuple(return_list)


def substitute_template(string, substitution_dict):
    """Substitute in the given string the placeholders with the values defined in
    substitution_dict.

    The placeholders are defined by two pairs of curly parentheses, ``{{key}}``. Default
    values can be specified after the double colon, for example, to set the default value
    of ``key`` to ``10``: ``{{key::10}}``.

    """
    # TODO: Add way to escape {{}} and ::, possibly with \

    # Let us see what is happening here.
    #
    # We define a large capturing group that matches objects of the form {{test}} or
    # {{test::bob123}}
    #
    # We match the {{ }} literally, inside we have a second capturing group (\w+?) that
    # matches a word, then we have a third capturing group (::(.*?))? which checks if
    # there are default value. This group matches the literal :: with anything after that
    # (.*?), in the last capturing group. Note that we use the +? and *? operators. These
    # are the non-greedy version of + and *. We need them because otherwise we would match
    # multiple placeholders in one.

    rx = re.compile(r"({{(\w+?)(::(.*?))?}})")

    # We make a copy of the string, since we are going to modify it
    out_string = string[:]

    LOGGER.debug(f"string = {string}")

    # Now, we iterate over the matches and substitute the correct value in the string
    for placeholder, key, has_default, default_value in rx.findall(string):
        LOGGER.debug(f"placeholder = {placeholder}")
        LOGGER.debug(f"key = {key}")
        LOGGER.debug(f"has_default = {has_default}")
        LOGGER.debug(f"default_value = {default_value}")
        if key in substitution_dict:
            out_string = re.sub(placeholder, substitution_dict[key], out_string)
        else:
            # We don't have the key in substitution_dict
            if has_default:
                LOGGER.debug("Substituting default")
                out_string = re.sub(placeholder, default_value, out_string)
            else:
                raise RuntimeError(f"Substitution dictionary does not have key {key}")
        LOGGER.debug(f"out_string = {out_string}")

    return out_string


def run_commands(list_, parallel=False) -> None:
    """Run all the commands in the given list.

    :param list_: List of commands that have to be run.
    :type list_: tuple of str
    :param parallel: Whether to run the commands in parallel.
    :type parallel: bool
    """
    # TODO: Add option to run commands in parallel

    for cmd in list_:
        LOGGER.info(f"Running command:\n{cmd}")

        # The function parser.prepare_commands returns a list of strings, but subprocess
        # doesn't want a string, it wants a list with command and arguments. So, we split
        # the lists. This may seem additional work, since we made the effort to join the
        # lists in parser.prepare_commands, but doing this allows us to process an
        # arbitrary number of arguments at each level of the config file.
        retcode = subprocess.run(cmd.split()).returncode
        LOGGER.info(f"Return code {retcode}")


def main():

    # These are not allowed because they are used to control ciak
    keys_not_allowed = ["ciakfile", "parallel", "verbose"]

    desc = f"""Orchestrate the execution of a series of commands using ciak files.
A ciak file is a special config file that defines what commands you want to run.

Note: the keys {keys_not_allowed} are not allowed (as they are used to control the
    program)."""

    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument("-c", "--ciakfile", help="Path of the ciak file", required=True)
    parser.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )
    parser.add_argument(
        "--parallel", help="Run commands in parallel", action="store_true"
    )

    args, unknown = parser.parse_known_args()

    # We add all the unknown to the parser. This allows the user to set any key they
    # want just by adding them to the list of cli arguments. For example --test bob
    # will substitute the 'test' placeholder with 'bob'.
    for arg in unknown:
        if arg.startswith(("-", "--")):
            parser.add_argument(arg.split('=')[0])

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format="%(asctime)s - %(message)s")
        LOGGER.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s")
        LOGGER.setLevel(logging.INFO)

    # Get argparse namespace as dictionary
    substitution_dict = vars(args).copy()
    LOGGER.debug(f"substitution_dict = {substitution_dict}")

    # Remove the keys that are reserved
    for key in keys_not_allowed:
        del substitution_dict[key]

    # Do everything that needs to be done
    commands = tuple(
        substitute_template(cmd, substitution_dict)
        for cmd in prepare_commands(read_asterisk_lines_from_file(args.ciakfile))
    )

    run_commands(commands)
