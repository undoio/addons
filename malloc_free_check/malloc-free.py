#! /usr/bin/env udb-automate
"""
Undo Automation command-line script for tracking calls to malloc() and free() and checking for
leaked memory.

This script only support the x86-64 architecture.

Contributors: Chris Croft-White, Magne Hov
"""

import sys
import textwrap

from undo.udb_launcher import REDIRECTION_COLLECT, UdbLauncher


def main(argv):
    # Get the arguments from the command line.
    try:
        recording = argv[1]
    except ValueError:
        # Wrong number of arguments.
        print(f"{sys.argv[0]} RECORDING_FILE", file=sys.stderr)
        raise SystemExit(1)

    # Prepare for launching UDB.
    launcher = UdbLauncher()
    # Make UDB run with our recording.
    launcher.recording_file = recording
    # Make UDB load the malloc_free_check_extension.py file from the current directory.
    launcher.add_extension("malloc_free_check_extension")
    # Finally, launch UDB!
    # We collect the output as, in normal conditions, we don't want to show it
    # to the user but, in case of errors, we want to display it.
    res = launcher.run_debugger(redirect_debugger_output=REDIRECTION_COLLECT)

    if res.exit_code == 0:
        # All good as UDB exited with exit code 0 (i.e. no errors).
        # The result_data attribute is used to pass information from the extension to this script.
        unmatched = res.result_data["unmatched"]
        print(f"The recording failed to free allocated memory {unmatched} time(s).")
    else:
        # Something went wrong! Print a useful message.
        print(
            textwrap.dedent(
                f"""\
                Error!
                UDB exited with code {res.exit_code}.

                The output was:

                {res.output}
                """
            ),
            file=sys.stderr,
        )
        # Exit this script with the same error code as UDB.
        raise SystemExit(res.exit_code)


if __name__ == "__main__":
    main(sys.argv)
