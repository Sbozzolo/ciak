<p align="center">
<img src="https://github.com/Sbozzolo/ciak/raw/main/logo.png" width="534" height="178">
</p>

[![PyPI version](https://badge.fury.io/py/ciak.svg)](https://badge.fury.io/py/ciak)
[![Test](https://github.com/Sbozzolo/ciak/actions/workflows/test.yml/badge.svg)](https://github.com/Sbozzolo/ciak/actions/workflows/test.yml)
[![Coverage](https://codecov.io/github/Sbozzolo/ciak/branch/main/graph/badge.svg?token=0D6WFHT1UQ)](https://codecov.io/github/Sbozzolo/ciak)

`ciak` is a Python program to run executables according to a configuration file
(a *ciakfile*) optionally containing user-declared variables that can be
adjusted at runtime.

A ciakfile is a simple text file that describes a nested tree using asterisks
and that has placeholders for runtime-controllable variables, supporting
defaults. Thanks to the nested tree structure, the amount of typing required is
drastically reduced when the same commands have to be executed multiple times
but with different arguments. On the other hand, support for placeholders allows
for code reuse and the same ciakfile can be used for different situations. This
is facilitated by the fact that if you define an environmental variable
`CIAKFILES_DIR`, `ciak` will know where to look for your ciakfiles, so you can
call them from anywhere in your system. Finally, in ciakfiles, every line that
does not start with an asterisk (up to leading spaces) is treated as a comment.
With this feature, one can write extensive commentaries that perfectly blend in
with the configuration itself.

For an example of use case, see the section ["Complete explanation of a specific
use case"](https://github.com/Sbozzolo/ciak#going-over-a-specific-use-case). See
below for an example of what a configuration file looks like.

## Getting started

`ciak` is available on PyPI. You can install it with `pip`:

``` sh
pip3 install ciak
```
`ciak` requires `python >= 3.9` and has no external runtime dependency.
See [ciak36](https://github.com/Sbozzolo/ciak#ciak36) for compatibility with previous
versions of Python.

The best way to get started with `ciak` is to check the
[examples](https://github.com/Sbozzolo/ciak#examples) out.

### Examples

In this Section, we are going to explore the various ways in which `ciak` can be
used, form the simplest, to the most complex.

#### Level 0: To run a list of command-line instructions

Suppose you want to execute a set of command-line instructions. For instance,
creating a folder, creating three empty files, and moving them inside the folder. (This is a contrived
example, but we are going to build upon this later.) A shell script for this
task might look like:
``` sh
mkdir myfolder
touch myfolder/first
touch myfolder/second
touch myfolder/third
```
This can be easily converted into a ciakfile by prepending asterisks in front of
each line:
``` org
* mkdir myfolder
* touch first
* touch second
* touch third
* mv first second third myfolder
```
Now, assuming this is saved into a `ciak0.org`, it can be executed with
``` sh
ciak -c ciak0.org
```
Our `ciak0.org` contains some redundancies: we run `touch` three times. With `ciak`,
we can express this more tersely by adding one nesting level
``` org
* mkdir myfolder
* touch
** first
** second
** third
* mv first second third myfolder
```
Saving this into `ciak01.org` and executing with `ciak -c ciak1.org` will produce
the same result as before. ciakfiles represent sequences of commands using nested trees,
so that similar commands can be executed with minimal variation. ciakfiles are meant to
be self-documenting: every line that does not start with an asterisk is a comment, so we
can expand our example:
``` org
* mkdir myfolder
  First, we create our target folder. We will place everything inside here.
* touch
  Next, we create three files (`first`, `second`, `third`).
** first
** second
** third
* mv first second third myfolder
  We move the three files inside our target folder.
```

#### Level 1: To parallelize the execution of certain instructions

Building upon our example, `ciak` supports mixing parallel and serial blocks.
For instance, we can demand that the three files `first`, `second`, `third` are
created in parallel. To do so, we add `* # BEGIN_PARALLEL` and `* #
END_PARALLEL` clauses:
``` org
* mkdir myfolder
  First, we create our target folder. We will place everything inside here.
* # BEGIN_PARALLEL
* touch
  Next, we create three files (`first`, `second`, `third`).
** first
** second
** third
* # END_PARALLEL
* mv first second third myfolder
  We move the three files inside our target folder.
```
Saving this to `ciak1.org`, and executing with `ciak -c ciak1.org`, `ciak` will
execute instructions serially, until it finds a parallel block, which is then executed
in parallel (with as many cores as available), and then it goes back to running commands
serially. The flag `--no-parallel` transforms parallel blocks into serial ones.

#### Level 2: To parametrize the execution of certain instructions

ciakfiles are can contain placeholders values that are controlled at runtime.
This makes `ciak` powerful and promotes code reuse. The syntax for command-line
adjustable placeholders is `{{key::default_value}}`.

Consider the simple ciakfile is
``` org
* ls {{pwd::/tmp}}
```
Assuming we save the file to `ciak2.org`, we can then run
``` sh
ciak -c ciak2.org --pwd $HOME
```
This will execute the command `ls $HOME`. If we were to run
``` sh
ciak -c ciak2.org
```
then the default value for `pwd` is used and the command `ls /tmp` is run instead.

We can extend our previous example:
``` org
* mkdir {{dest::myfolder}}
  First, we create our target folder. We will place everything inside here.
* # BEGIN_PARALLEL
* touch
  Next, we create three files (`first`, `second`, `third`).
** first
** second
** third
* # END_PARALLEL
* mv first second third myfolder
  We move the three files inside our target folder.
```
Now, we can control the destination folder when running with through the `--dest `
flag.

#### Level 3: To write complex workflows once, and use them over and over

We saw that we can produce complex ciakfiles that can be controlled via the
command line. The last piece of the puzzle is `CIAKFILES_DIR`. If you set this
environmental variable to a folder, `ciak` will try to find ciakfiles in that
folder (by default it is `.`). So, with `ciak`, you can write complex and
general workflows and easily invoke them from anywhere in your filesystem. For
instance, if you have a ciakfile named `compute_result` that defined a
``{{datadir::.}}`` argument in your `CIAKFILES_DIR`, you can navigate to the
folder where you have the data and execute `ciak compute_result`. Check the
section on [ciak and
org-mode](https://github.com/Sbozzolo/ciak#ciak-and-org-mode) out to see a
real-life example.

## The ciakfile configuration syntax

Valid ciakfiles are text files with the following characteristics:
- Lines that do no start with asterisk (up to initial spaces) are considered
  comments.
- The number of asterisks defines the level in the three and the parent of an
  item is the first item with fewer asterisk above it.
- Executables have to be on the first level of the tree.
- Placeholders can be defined with the syntax `{{key::default_value}}`. These
  will be substituted at runtime with values specified via command-line or with
  the default value.
- Indentation, leading/trailing spaces, and file extension do not matter.
- Parallel blocks must be at the top level (only one asterisk), they start with
  `# BEGIN_PARALLEL` and end with `# END_PARALLEL`. Nested parallel blocks will
  be ignored.

## Why should I use ciak instead of a shell script?

At a first glance, `ciak` may seem just a convoluted way to write a shell
script. This is not the case: `ciak` enables workflows that are impractical with
shell script. The main advantages of `ciak` are:

- Simplify repeated arguments across multiple scripts
- Easily add keyword arguments with defaults
- Have parallelization with no effort
- Strong emphasis on self-documentation

However, by design, `ciak` does not support any shell feature (like input/output
redirection, for loops, variable assignment, ...).

`ciak` can trivially parallelize the execution of some commands. Hence, you can
use it as a replacement of [GNU
Parallel](https://www.gnu.org/software/parallel/) to parallelize commands
defined in a configuration file.

### ciak36

`ciak` uses features available only with Python3.9 or later versions. For
convenience, an executable `ciak36` is provided, compatible with Python3.6.
There is no difference in features available between `ciak` and `ciak36`.
`ciak36` is automatically generated by `ciak` with the `generate_ciak36.sh`
script. `ciak36` will be dropped in the future.

### ciak and org-mode

`ciak` borrows its syntax from [GNU Emacs](https://gnu.org/software/emacs/)'s
[org-mode](https://orgmode.org) . As such, if you save your ciakfiles with
extension `.org` and you open them with Emacs, you gain access to a large number
of additional features (e.g., automatic coloring and indentation, subtree
folding, tables, exporting to different formats, ...). This is what an example
of a ciakfile will look like in (customized) Emacs

![org-mode
screenshot](https://github.com/Sbozzolo/ciak/raw/main/ss-org-mode.png)

Using org-mode greatly enhances `ciak`'s self-documenting capabilities.

## Options

`--fail-fast`, if enabled, `ciak` stops as soon as a non-zero return code is
found.

`--no-parellel`, if enabled, the commands are executed serially. By defaults,
commands are executed in parallel with a number of workers that is equal to the
number of available cores on the machine.

`--dry-run`, if enabled, `ciak` will print the command that would be executed,
without executing any.

## Development

We use:
* [Poetry](https://python-poetry.org) to manage dependencies, build, and publish
  `motionpicture`.
* [Black](https://github.com/psf/black) for formatting the code (with 89
  columns).
* [pytest](https://pytest.org) for unit tests.
* [coverage](https://coverage.readthedocs.io/en/) for test coverage.
* [mypy](https://mypy.readthedocs.io/) for static type analysis.
* [isort](https://isort.readthedocs.io/) to sort the import statements.
* [flake8](https://flake8.pycqa.org/) for general static analysis.
* [pre-commit](https://pre-commit.com/) to apply linting rules before commits.
* GitHub actions for continuous integration.

We are happy to accept contributions.

## What does ciak mean?

In Italian, the word *ciak* is an onomatopoeia that indicates the sound of the
clapperboard used by movie directors to kick off the recording of a scene. Along
the same lines, when you use this program, you are the script-writer and the
director: you define what needs to be run in the ciakfile and you start and
control its execution with `ciak`, your clapperboard.

## Going over a specific use case

`ciak` was developed to run analysis of [Einstein
Toolkit](http://einsteintoolkit.org) simulations using
[kuibit](https://github.com/Sbozzolo/kuibit). `ciak` solves four problems:
1. Simplification in writing the analysis
2. Reuse of the code
3. Reproducibility and self-documentation in the analysis
4. Parallelization of analysis

Normally, one runs several simulations of the same kind with only a handful of
parameters changed. The entire analysis can be condensed into a ciakfile which
takes as command-line input the folder with the simulation output.

Moreover, distributing the ciakfile along with the scripts that are called
allows other people to easily reproduce the analysis. The comments in the
ciakfile are helpful to explain what is going on and why certain values are set
at the values they are set.
