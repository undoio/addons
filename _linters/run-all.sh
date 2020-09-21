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

function join() {
    local IFS="$1"
    shift
    echo "$*"
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


# Black

echo "== BLACK == "

"${linters_dir}/run-black.sh" \
    --check \
    "${py_files[@]}"
error_or_success $?


# Pylint

echo "== PYLINT == "

python3 -m pylint \
    --rcfile=_linters/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
error_or_success $?


# Mypy

echo "== MYPY == "

export MYPYPATH=_linters/mypy-stubs
python3 -m mypy \
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
