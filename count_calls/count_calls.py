#! /usr/bin/env udb-automate

from __future__ import absolute_import, division, print_function

import sys
import textwrap

from undodb.udb_launcher import (
    REDIRECTION_COLLECT,
    UdbLauncher,
    )


def main(argv):
    # Get the arguments from the command line.
    try:
        recording, func_name = argv[1:]
    except ValueError:
        # Wrong number of arguments.
        print('{} RECORDING_FILE FUNCTION_NAME'.format(sys.argv[0]))
        raise SystemExit(1)

    # Prepare for launching UDB.
    launcher = UdbLauncher()
    # Make UDB run with our recording.
    launcher.recording_file = recording
    # Make UDB load the count_calls_extension.py file from the current
    # directory.
    launcher.add_extension('count_calls_extension')
    # Tell the extension which function name it needs to check.
    # The run_data attribute is a dictionary in which arbitrary data can be
    # stored and passed to the extension (as long as it can be serialised using
    # the Python pickle module).
    launcher.run_data['func_name'] = func_name
    # Finally, launch UDB!
    # We collect the output as, in normal conditions, we don't want to show it
    # to the user but, in case of errors, we want to display it.
    res = launcher.run_debugger(redirect_debugger_output=REDIRECTION_COLLECT)

    if res.exit_code == 0:
        # All good as UDB exited with exit code 0 (i.e. no errors).
        print('The recording hit "{}" {} time(s).'.format(
            func_name,
            # The result_data attribute is analogous to UdbLauncher.run_data but
            # it's used to pass information the opposite way, from the extension
            # to this script.
            res.result_data['hit-count'],
            ))
    else:
        # Something went wrong! Print a useful message.
        print(
            textwrap.dedent(
                '''\
                Error!
                UDB exited with code {res.exit_code}.

                The output was:

                {res.output}
                ''').format(res=res),
            file=sys.stderr,
            )
        # Exit this script with the same error code as UDB.
        raise SystemExit(res.exit_code)


if __name__ == '__main__':
    main(sys.argv)
