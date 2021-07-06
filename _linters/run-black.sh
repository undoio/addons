#! /bin/bash

exec python3 -m black \
    --target-version py36 \
    --line-length 100 \
    "$@"
