import pathlib


def maybe_install_script(script_path: pathlib.Path, script_name: str) -> None:
    """
    Ask for permission and then install a script into ~/.local/bin.
    """
    local_bin = pathlib.Path.home() / ".local" / "bin"
    install_path = local_bin / script_name

    choice = input(f"Do you want to install {script_name} to {local_bin}? [y/N] ")
    if choice.lower() not in ("y", "yes"):
        return

    try:
        install_path.symlink_to(script_path)
        install_path.chmod(0o755)
    except OSError as e:
        print(f"Failed to install the script: {e}")


script = pathlib.Path(__file__).resolve().parent / "malloc_free_check.py"

print(
    f"""\
The {script.name!r} script can be run outside of UDB:

     $ {script} <recording-file>
"""
)

maybe_install_script(script, "malloc-free-check")
