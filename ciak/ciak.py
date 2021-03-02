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

"""``ciak`` runs executables according to a configuration file (a ciakfile) that
optionally contains user-declared variables which can be adjusted at runtime.


The flow of this code is:

1. :py:func:`~.main` reads in what ciakfile the user wants to run and what variables are
   defined at runtime.

2. The file is read by :py:func:`~.read_asterisk_lines_from_file` and parsed by
   :py:func:`~.prepare_commands` to prepare a list of string that are going to be
   executed.

3. Looping over this list with :py:func:`~.substitute_template`, the placeholders in the
   ciakfile are substituted with the default values or the runtime variables.

4. The commands are executed by :py:func:`~.run_commands`.

The :py:mod:`~.parser` module reads files and parse the content according to a syntax
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

In visual form, this corresponds to the tree:

.. code-block

        (1)        (5)
       |   |
      (2) (3)
           |
          (4)

These will identify all the commands and arguments that ``ciak`` has to run. We walk
through the tree to prepare the list of the commands. In this example, we would have
``(1) (2)`` and ``(1) (3) (4)``.

"""

import argparse
import logging
import os
import subprocess
import re

LOGGER = logging.getLogger(__name__)

# ^ matches the beginning of the line
# (\s)? matches any number of whitespaces
# (\*)+ matches one or more asterisk
# (\s)? matches any number of whitespaces
_ASTRISK_REGEX = r"^(\s)*(\*)+(\s)*"


def read_asterisk_lines_from_file(path: str) -> tuple[str, ...]:
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


def prepare_commands(list_: tuple[str, ...]) -> tuple[str, ...]:
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


def substitute_template(string: str, substitution_dict: dict[str, str]) -> str:
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

    LOGGER.debug(f"{string =}")

    # Now, we iterate over the matches and substitute the correct value in the string
    for placeholder, key, has_default, default_value in rx.findall(string):
        LOGGER.debug(f"{placeholder =}")
        LOGGER.debug(f"{key =}")
        LOGGER.debug(f"{has_default =}")
        LOGGER.debug(f"{default_value =}")
        if key in substitution_dict:
            out_string = re.sub(placeholder, substitution_dict[key], out_string)
        else:
            # We don't have the key in substitution_dict
            if has_default:
                LOGGER.debug("Substituting default")
                out_string = re.sub(placeholder, default_value, out_string)
            else:
                raise RuntimeError(f"Substitution dictionary does not have key {key}")
        LOGGER.debug(f"{out_string =}")

    return out_string


def get_ciakfile(args_ciakfile, args_ciakfile_path):
    """Parse arguments to find the full path of the requested ciakfile.

    If ``args_ciakfile`` is provided, then we try to use it looking at the folder defined
    by the environmental variable CIAKFILES_DIR (or '.' if the variable is not defined).
    If it is not provided, we look at ``args_ciakfile_path``.

    :param args_ciakfile: Name of the ciakfile (full name with extension).
    :type args_ciakfile: str
    :param args_ciakfile_path: Full path of a ciakfile.
    :type args_ciakfile_path: str

    """
    if args_ciakfile:
        if os.environ['CIAKFILES_DIR']:
            return os.path.join(os.environ['CIAKFILES_DIR'], args_ciakfile)
        return args_ciakfile

    raise RuntimeError("One between ciakfile and --ciakfile-path is required")


def run_commands(
    list_: tuple[str], fail_fast: bool = False, parallel: bool = False
) -> None:
    """Run all the commands in the given list.

    :param list_: List of commands that have to be run.
    :type list_: tuple of str
    :param fail_fast: If True, stop the execution as soon as a command returns a non-zero
                      error code.
    :type fail_fast: bool
    :param parallel: Whether to run the commands in parallel.
    :type parallel: bool

    """
    # TODO: Add option to run commands in parallel
    if parallel:
        raise NotImplementedError("Parallel execution is not implemented yet")

    for cmd in list_:
        LOGGER.info(f"Running command:\n{cmd}")

        # The function parser.prepare_commands returns a list of strings, but subprocess
        # doesn't want a string, it wants a list with command and arguments. So, we split
        # the lists. This may seem additional work, since we made the effort to join the
        # lists in parser.prepare_commands, but doing this allows us to process an
        # arbitrary number of arguments at each level of the config file.
        retcode = subprocess.run(cmd.split()).returncode
        LOGGER.debug(f"Return code {retcode}")
        if fail_fast and retcode != 0:
            LOGGER.info(f"Command return with code {retcode}, aborting")
            return


def main():

    # These are not allowed because they are used to control ciak
    reserved_keys = ["ciakfile", "fail_fast", "parallel", "verbose"]

    desc = f"""Orchestrate the execution of a series of commands using ciak files.
A ciak file is a special config file that defines what commands you want to run.

When declaring variables in the file, - are turned into _.

Note: the keys {reserved_keys} are not allowed (as they are used to control the
    program)."""

    parser = argparse.ArgumentParser(description=desc)

    parser.add(
        "ciakfile",
        nargs="?",
        help="Ciakfile to use among the ones found in CIAKFILES_DIR."
        "If CIAKFILES_DIR is not defined, then '.' is assumed."
    )
    parser.add_argument("-c", "--ciakfile-path",
                        help="Path of the ciak file")
    parser.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )

    parser.add_argument(
        "--fail-fast",
        help="Stop execution if a command returns a non-zero error code",
        action="store_true",
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
            parser.add_argument(arg.split("=")[0])

    args = parser.parse_args()

    ciakfile = get_ciakfile(args.ciakfile, args.ciakfile_path)

    if args.verbose:
        logging.basicConfig(format="%(asctime)s - %(message)s")
        LOGGER.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s")
        LOGGER.setLevel(logging.INFO)

    # Get argparse namespace as dictionary
    substitution_dict = vars(args).copy()
    LOGGER.debug(f"{substitution_dict =}")

    # Remove the keys that are reserved
    for key in reserved_keys:
        del substitution_dict[key]

    # Do everything that needs to be done
    commands = tuple(
        substitute_template(cmd, substitution_dict)
        for cmd in prepare_commands(read_asterisk_lines_from_file(ciakfile))
    )

    run_commands(commands, parallel=args.parallel, fail_fast=args.fail_fast)
