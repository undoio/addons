#! /usr/bin/env udb-automate

from __future__ import absolute_import, division, print_function

import sys
import textwrap

from undodb.udb_launcher import (
    REDIRECTION_COLLECT,
    UdbLauncher,
    )


def main(argv):
    # Get the arguments.
    try:
        recording, func_name = argv[1:]
    except ValueError:
        print('{} RECORDING_FILE FUNCTION_NAME'.format(sys.argv[0]))
        raise SystemExit(1)

    # Prepare for launching UndoDB.
    launcher = UdbLauncher()
    # Make UndoDB run with our recording.
    launcher.recording_file = recording
    # Make UndoDB load the count_calls_extension.py file from the current
    # directory.
    launcher.add_extension('count_calls_extension')
    # Tell the extension the function name.
    launcher.run_data['func_name'] = func_name
    # Finally, launch UndoDB! (And hide the output, we don't want it on screen.)
    res = launcher.run_debugger(redirect_debugger_output=REDIRECTION_COLLECT)

    if res.exit_code == 0:
        # All good.
        print('The recording hit "{}" {} time(s).'.format(
            func_name,
            res.result_data['hit-count'],
            ))
    else:
        # Something went wrong! Print a useful message.
        print(textwrap.dedent(
            '''\
            Error!
            UndoDB exited with code {res.exit_code}.

            The output is:
            {div}
            {res.output}
            {div}\
            ''').format(
                res=res,
                div='-' * 72,
                ))
        raise SystemExit(res.exit_code)


if __name__ == '__main__':
    main(sys.argv)
