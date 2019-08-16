#! /bin/bash

readonly bash_source="${BASH_SOURCE[0]:-$0}"
readonly linters_dir=$(dirname "$bash_source")
readonly top_dir=$(realpath "$linters_dir/..")

function error_exit() {
    for str in "$@"; do
        echo -n "$str" >&2
    done
    echo >&2

    exit 1
}

failure_count=0
total_count=0

function error_or_success() {
    ret="$1"
    echo
    if [[ "$ret" = 0 ]]; then
        echo "Success!"
    else
        echo "Failed!"
        ((failure_count++))
    fi
    ((total_count++))
    echo
}

cd "$top_dir" || error_exit "Cannot change directory to $top_dir"

declare py_files=()
# --full-name means we get the path relative to the top directory.
# -z means that the file names are \0 separated.
while IFS= read -r -d $'\0'; do
    if [[ "$REPLY" = *.py ]]; then
        py_files+=("$REPLY")
    fi
done < <(git ls-files --full-name -z)

[[ ${#py_files[@]} != 0 ]] || error_exit "No Python files in the repository?"


# Pylint

echo "== PYLINT == "

pylint \
    --rcfile=_linters/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
error_or_success $?


# Pylint (Python 3 mode)

echo "== PYLINT (PYTHON 3 MODE) == "

pylint \
    --py3k \
    --disable useless-suppression \
    --rcfile=_linters/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
error_or_success $?


# Pycodestyle

echo "== PYCODESTYLE == "

pycodestyle_ignore=(
    '--ignore=E123' # Closing bracket indentation. Checked by pylint.
    '--ignore=E124' # Closing bracket not aligned. Pylint has different opinions.
    '--ignore=E241' # Multiple spaces after colon. Allowed for dicts.
    '--ignore=E261' # Two spaces before inline comment.
    '--ignore=E266' # Too many "#". It's useful to define blocks of code.
    '--ignore=E402' # Module level import not at the top. Checked by pylint.
    '--ignore=E501' # Line too long. Checked by pylint.
    '--ignore=E701' # Multiple statements in one line. Checked by pylint.
    '--ignore=E722' # Bare except. Checked by pylint.
    '--ignore=E731' # Do not assign lambda. Needed when defining argument to avoid a function redef error.
    '--ignore=E741' # Ambiguous variable name. Pylint already checks for names.
    '--ignore=W504' # Line break after binary operator. This is the recommended style (503 is the opposite).
    )
pycodestyle \
    "${pycodestyle_ignore[@]}" \
    "${py_files[@]}"
error_or_success $?


# Mypy

echo "== MYPY == "

export MYPYPATH=_linters/mypy-stubs
mypy \
    --follow-imports=silent \
    --config-file=_linters/mypy.ini \
    "${py_files[@]}"
error_or_success $?


# Done!

if [[ $failure_count = 0 ]]; then
    echo "All tests passed"
else
    echo "Failures: $failure_count out of $total_count tests"
fi
exit $failure_count
