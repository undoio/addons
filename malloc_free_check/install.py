import pathlib


script = pathlib.Path(__file__).resolve().parent / "malloc_free_check.py"

print(
    f"""\
The {script.name!r} script can be run outside of UDB:

     $ {script} <recording-file>
"""
)
