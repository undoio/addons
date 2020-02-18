Load symbols lazily
===================

Loads only the debugging symbols effectively used
in the recording.

To use:

  1. start UDB with no parameters: `udb`
  2. load the recording lazily: `loadlazy <recording file>`
  3. to populate a backtrace that is showing no symbols: `popbt`
  4. to try and load the relevant symbols given a name: `loadsymlib <string>`
  5. to reverse-step at function boundaries when the caller might not have symbols
     loaded: `rss`

NOTE: loadsymlib is slow and it does not guarantee good results as yet.
