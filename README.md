<p align="center">
<img src="https://github.com/Sbozzolo/ciak/raw/main/logo.png" width="534" height="178">
</p>

*README/DOCUMENTATION IS WORK IN PROGRESS*

`ciak` is a Python program that runs executables according to a configuration
file (a *ciakfile*) that optional contains user-declared variables which can be
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

For an example of use case, see the section "Complete explanation of a specific
use case" [TODO: Add link here]. See below for an example of what a
configuration file looks like.

# Installation

`ciak` is available on PyPI. You can install it with `pip`:

``` sh
pip3 install ciak
```
`ciak` requires Python3.9 and has no external dependency.
See ciak36 [TODO: ADD LINK HERE] for compatibility with previous versions of Python.

## Why should I use ciak instead of a shell script?

At a first glance, `ciak` may seem just a convoluted way to write a shell
script. This is not the case: `ciak` enables workflows that are impractical with
shell script. The main advantages of `ciak` are:

- Simplify repeated arguments across multiple scripts
- Use keyword arguments
- Have parallelization with no effort
- Strong emphasis on self-documentation

However, by design, `ciak` does not support any shell feature (like input/output
redirection, for loops, variable assignment, ...).

## ciak36

`ciak` uses features available only with Python3.9 or later versions. For
convenience, an executable `ciak36` is provided, compatible with Python3.6.
There is no difference in features available between `ciak` and `ciak36`.
`ciak36` is automatically generated by `ciak` with the `generate_ciak36.sh`
script. `ciak36` will be dropped in the future.

# The ciakfile configuration syntax

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

## Examples

A simple ciakfile is
``` org
* ls {{pwd::/tmp}}
```
Assuming we save the file to `ciak1.org`, we can then run
``` sh
ciak -c ciak1.org --pwd $HOME
```
This will execute the command `ls $HOME`. If we were to run
``` sh
ciak -c ciak1.org
```
then the default value for `pwd` is used and the command `ls /tmp` is run instead.

In a more slightly interesting example, we want to compress different
files. This can be achieved with
``` org
* gzip
** file1
** file2
** file3
** file4
```
Saving this as `ciak2.org`, running
``` sh
ciak -c ciak2.org
```
will correspond to running `gzip file1`, `gzip file2`, ....

It is possible to parallelize the execution of certain sections of the file with
the tags `# BEGIN_PARALLEL` and `# END_PARALLEL`. At the moment, these have to be at
the top level. For example,
``` org
* # BEGIN_PARALLEL
* gzip
** file1
** file2
** file3
** file4
* # END_PARALLEL
```

In this case, `ciak` will use as many processes as the number of cores
available.

## ciak and org-mode

`ciak` borrows its syntax from [GNU Emacs](https://gnu.org/software/emacs/)'s
[org-mode](https://orgmode.org) . As such, if you save your ciakfiles with
extension `.org` and you open them with Emacs, you gain access to a large number
of additional features (e.g., automatic coloring and indentation, subtree
folding, tables, exporting to different formats, ...). This is what an example
of a ciakfile will look like in (customized) Emacs

![org-mode
screenshot](https://github.com/Sbozzolo/ciak/raw/main/ss-org-mode.png)

Using org-mode greatly enhances `ciak`'s self-documenting capabilities.

# Options

`--fail-fast`, if enabled, `ciak` stops as soon as a non-zero return code is
found.

`--no-parellel`, if enabled, the commands are executed serially. By defaults,
commands are executed in parallel with a number of workers that is equal to the
number of available cores on the machine.

`--dry-run`, if enabled, `ciak` will print the command that would be executed,
without executing any.

# Development

We use:
* [Poetry](https://python-poetry.org) to manage dependencies, build, and publish
  `motionpicture`.
* [Black](https://github.com/psf/black) for formatting the code (with 89
  columns).
* [pytest](https://pytest.org) for unit tests (with `pytest-cov` for test
  coverage).
* [mypy](https://mypy.readthedocs.io/) for static type analysis.
* [isort](https://isort.readthedocs.io/) to sort the import statements.
* [flake8](https://flake8.pycqa.org/) for general static analysis.
* [pre-commit](https://pre-commit.com/) to apply linting rules before commits.
* GitHub actions for continuous integration.

We are happy to accept contributions.

# What does ciak mean?

In Italian, the word *ciak* is an onomatopoeia that indicates the sound of the
clapperboard used by movie directors to kick off the recording of a scene. Along
the same lines, when you use this program, you are the script-writer and the
director: you define what needs to be run in the `ciakfile` and you start and
control its execution with `ciak`, your clapperboard.

# Going over a specific use case

`ciak` was developed to run analysis of [Einstein
Toolkit](http://einsteintoolkit.org) simulations using
[kuibit](https://github.com/Sbozzolo/kuibit). `ciak` solves four problems:
1. Simplification in writing the analysis
2. Reuse of the code
3. Reproducibility and self-documentation in the analysis
4. Parallelization of analysis

Normally, one runs several simulations of the same kind when only a few
parameters are changed.

Distributing the `ciakfile` along with the scripts that are called allows other
people to easily reproduce the analysis. The comments in the `ciakfile` are
helpful to explain what is going on and why certain values are set at the values
they are set.
