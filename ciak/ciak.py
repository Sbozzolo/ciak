#!/usr/bin/env python3

# Copyright (C) 2021-2022 Gabriele Bozzola
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

"""``ciak`` runs executables according to a configuration file.

``ciak`` orchestrates the execution of command-line programs as defined by text
files. Such configuration files, known as ciakfiles, can optionally contains
user-declared variables which can be adjusted at runtime.

``ciak`` reads files and parse the content according to a syntax based on asterisks.
``ciak`` ignores all the lines that do not start with asterisks (up to initial spaces),
and reads the content as a tree with 'level' determined by the number of asterisks. For
example:

.. code-block

   # This is a comment
   ! This is a comment too
   * This is a first level item (1)
   ** This is a second level item (2)
      This is a command. Everything that does not start with `*` is a comment
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

It is possible to mark some portion of the tree as "PARALLEL", meaning that they can be
executed in parallel. This is done with the # BEGIN_PARALLEL and # END_PARALLEL
instructions. For example:

.. code-block

   * mkdir report
   * # BEGIN_PARALLEL
   ** touch report/first
   ** touch report/second
   * # END_PARALLEL
   * rm report

In this case, first a ``report`` folder is created. Then, two empty files are created in
that folder in parallel. Finally, the folder is deleted.

.. warning::

   At the moment, parallel blocks can only be at the top level of the tree.

The previous block is equivalent to:

.. code-block

   * mkdir report
   * # BEGIN_PARALLEL
   ** touch
   *** report/first
   *** report/second
   * # END_PARALLEL
   * rm report

Here, we specified the command (``touch``) once, and the various arguments (called in
different invocations of ``touch``) in nested levels.

What makes ``ciak`` powerful is its templating system: ``ciakfiles`` can contain
variables that can be adjusted at runtime. For instance:

.. code-block

   * mkdir {{foldername::report}}
   * # BEGIN_PARALLEL
   ** touch
   *** report/first
   *** report/second
   * # END_PARALLEL
   * rm {{foldername::report}}

In this block, ``foldername`` becomes a command-line argument with ``report`` as default
value. This promotes code reuse.

"""

# The flow of this code is:

# 1. :py:func:`~.main` reads in what ciakfile the user wants to run and what variables are
#    defined at runtime.

# 2. The file is read by :py:func:`~.read_asterisk_lines_from_file`.

# 3. The output of :py:func:`~.read_asterisk_lines_from_file` is scanned for PARALLEL
#    blocks by :py:func:`~.extract_execution_blocks`, which individuates the commands
#    that can be executed in parallel.

# 4. Each block (parallel and not) is parsed by :py:func:`~.prepare_commands` to prepare a
#    list of string that are going to be executed.

# 4. For each block, we loop over this list with :py:func:`~.substitute_template`, the
#    placeholders in the ciakfile are substituted with the default values or the runtime
#    variables.

# 5. The commands are executed by :py:func:`~.run_commands`.


import argparse
import concurrent.futures
import dataclasses
import logging
import os
import re
import subprocess
import warnings
from typing import Optional

# What marks the beginning and end of a parallel block?
#
# * # BEGIN_PARELLEL
# * # END_PARALLEL
#
# The number of spaces around '#' does not matter
_PARALLEL_BEGIN = "BEGIN_PARALLEL"
_PARALLEL_END = "END_PARALLEL"

LOGGER = logging.getLogger(__name__)

# ^ marks the beginning of the line
# \s* matches any number of whitespaces
# \*+ matches one or more asterisk
# \s* matches any number of whitespaces
_ASTERISK_REGEX = r"^\s*\*+\s*"

# ^ matches the beginning of the line
# \s* matches any number of whitespaces
# \* matches one or more asterisk
# \s* matches any number of whitespaces
# \# matches one instance of #
# \s* matches any number of whitespaces
# ({_PARALLEL_BEGIN}) matches one instance of _PARALLEL_BEGIN
# \s* matches any number of whitespaces
# ^ marks the end of the line
_PARALLEL_BEGIN_REGEX = rf"^\s*\*\s*\#\s*({_PARALLEL_BEGIN})\s*$"
_PARALLEL_END_REGEX = rf"^\s*\*\s*\#\s*({_PARALLEL_END})\s*$"


@dataclasses.dataclass(frozen=True)
class ExecutionBlock:
    """List of commands that can be all run in parallel or not.

    :ivar commands: Commands to be executed. These lines are all inside or outside a
                    PARALLEL block, so they can all be executed serially or in parallel.
    :ivar parallel: When parallel is True, the commands can be executed in parallel
    """

    commands: tuple[str, ...]
    parallel: bool


def read_asterisk_lines_from_file(path: str) -> tuple[str, ...]:
    """Read the file in ``path`` according to the ``ciak`` syntax.

    Read the file in ``path`` ignoring lines that do not start with asterisks (up to
    initial spaces).

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
        rx = re.compile(_ASTERISK_REGEX)
        return rx.match(string) is not None

    return tuple(filter(start_with_asterisk, lines))


def extract_execution_blocks(lines: tuple[str, ...]) -> tuple[ExecutionBlock, ...]:
    f"""Partition lines in execution blocks with commands that can be run in parallel or not.

    Search through the lines for ``# f{_PARALLEL_BEGIN}`` and ``# f{_PARALLEL_END}``.
    Then, return a list of blocks with lines that are all inside or all outside this
    markers. In this way, we identify the blocks that can be run in parallel and the ones
    that cannot.

    :param lines: Lines that start with asterisk in the file.
    :type lines: Tuple of strings
    :returns: List of :py:class:`~.ExecutionBlock` with consistent execution needs
              (all the lines can be executed at the same time or not).
    :rtype: tuple of :py:class:`~.ExecutionBlock`

    """
    begin_rx = re.compile(_PARALLEL_BEGIN_REGEX)
    end_rx = re.compile(_PARALLEL_END_REGEX)

    # block will contain the lines corresponding to the current block
    block: list[str] = []
    # return_list will be all the parsed ExecutionBlocks
    return_list = []

    inside_parallel_block = False

    for line in lines:
        if begin_rx.match(line):
            # We matched the beginning of a block, we have to flush out what we had
            # before
            if block:
                return_list.append(
                    ExecutionBlock(tuple(prepare_commands(block)), parallel=False)
                )
                block = []

            inside_parallel_block = True

            continue

        if end_rx.match(line):
            if inside_parallel_block:
                if block:
                    return_list.append(
                        ExecutionBlock(tuple(prepare_commands(block)), parallel=True)
                    )
                    block = []
                else:
                    warnings.warn("Found empty parallel block")

                inside_parallel_block = False
            else:
                # We match the end of a parallel block, but haven't matched the beginning
                raise RuntimeError("End of parallel block found before the beginning")

            continue

        block.append(line)

    if inside_parallel_block:
        raise RuntimeError("Missing end of parallel block")

    # We need to add the last group of lines
    if block:
        return_list.append(
            ExecutionBlock(tuple(prepare_commands(block)), parallel=False)
        )

    return tuple(return_list)


def prepare_commands(list_: list[str]) -> tuple[str, ...]:
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
    list_no_astr = tuple(map(lambda x: re.sub(_ASTERISK_REGEX, "", x), list_))

    return_list = []
    current_command = []
    for index, element in enumerate(list_no_astr):
        # Add the current element to the list current_command. We are going to keep
        # current_command updated with the new entries until we find a leaf of the tree.
        # At that point, we append current_command to return_list.
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
            # next item as fewer asterisks. If it is zero, then the next item is another
            # command, so this is a leaf.
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
    """Substitute in the given string the placeholders using ``substitution_dict``.

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


def get_ciakfile(
    args_ciakfile: Optional[str] = None, args_ciakfile_path: Optional[str] = None
) -> str:
    """Parse arguments to find the full path of the requested ciakfile.

    If ``args_ciakfile_path`` is provided, used that. Otherwise. If ``args_ciakfile`` is
    provided, then we try to use it looking at the folder defined by the environmental
    variable CIAKFILES_DIR (or '.' if the variable is not defined). The function raises
    an error if the file does not exist.

    :param args_ciakfile: Name of the ciakfile (full name with extension).
    :type args_ciakfile: str
    :param args_ciakfile_path: Full path of a ciakfile.
    :type args_ciakfile_path: str

    """
    if args_ciakfile_path is None:
        if args_ciakfile is None:
            raise RuntimeError("One between ciakfile and --ciakfile-path is required")

        # Here, args_ciakfile_path is None, but args_ciakfile is not. So, the path of
        # ciakfile was not provided, we will use the CIAKFILES_DIR. If CIAKFILES_DIR
        # is not provided, we will use the local folder
        prefix = os.environ.get("CIAKFILES_DIR", os.getcwd())
        args_ciakfile_path = os.path.join(prefix, args_ciakfile)

    # If we are here, args_ciakfile_path must have been set
    if os.path.isfile(args_ciakfile_path):
        return args_ciakfile_path
    raise RuntimeError(f"Ciakfile {args_ciakfile_path} does not exist")


def _run_one_command(cmd: str) -> int:
    """Run one given command.

    :param cmd: Command to be executed.
    :type cmd: str

    :returns: Return code.
    :rtype: int
    """
    LOGGER.info(f"Running command:\n{cmd}")
    # The function parser.prepare_commands returns a list of strings, but subprocess
    # doesn't want a string, it wants a list with command and arguments. So, we split the
    # lists. This may seem additional work, since we made the effort to join the lists in
    # parser.prepare_commands, but doing this allows us to process an arbitrary number of
    # arguments at each level of the config file.
    return subprocess.run(cmd.split()).returncode


def run_commands(
    list_: tuple[str, ...], fail_fast: bool = False, parallel: bool = False
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
    if parallel:
        if fail_fast:
            raise NotImplementedError(
                "Parallel execution with --fail-fast is not implemented yet"
            )
        with concurrent.futures.ProcessPoolExecutor() as executor:
            executor.map(_run_one_command, list_)
        return

    for cmd in list_:
        retcode = _run_one_command(cmd)
        LOGGER.debug(f"Return code {retcode}")
        if fail_fast and retcode != 0:
            LOGGER.info(f"Command return with code {retcode}, aborting")
            return


def main():
    """Run the entire program."""
    # These are not allowed because they are used to control ciak
    reserved_keys = ["ciakfile", "fail_fast", "no_parallel", "verbose"]

    desc = f"""Orchestrate the execution of a series of commands using ciak files.
A ciak file is a special config file that defines what commands you want to run.

When declaring variables in the file, - are turned into _.

Note: the keys {reserved_keys} are not allowed (as they are used to control the
    program)."""

    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument(
        "ciakfile",
        nargs="?",
        help="Ciakfile to use among the ones found in CIAKFILES_DIR."
        "If CIAKFILES_DIR is not defined, then '.' is assumed.",
    )
    parser.add_argument("-c", "--ciakfile-path", help="Path of the ciak file")
    parser.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )

    parser.add_argument(
        "--fail-fast",
        help="Stop execution if a command returns a non-zero error code",
        action="store_true",
    )

    parser.add_argument(
        "--dry-run",
        help="Print the list of commands to be executed, but do not run them.",
        action="store_true",
    )

    parser.add_argument(
        "--no-parallel",
        help="Ignore parallel blocks (run sequentially)",
        action="store_true",
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

    execution_blocks = extract_execution_blocks(read_asterisk_lines_from_file(ciakfile))

    for block in execution_blocks:
        # Extract commands as list of string, prepare them and run them.
        commands = tuple(
            substitute_template(cmd, substitution_dict)
            for cmd in prepare_commands(block.commands)
        )
        if args.dry_run:
            for cmd in commands:
                print(cmd)
        else:
            # We run the command in parallel if the block is set to be run in
            # parallel and if we parallel execution is not inhibited
            run_commands(
                commands,
                parallel=block.parallel and (not args.no_parallel),
                fail_fast=args.fail_fast,
            )
