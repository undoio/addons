Load symbols lazily
===================

Loads only the debugging symbols effectively used
in the recording.

To use:
  
  1) start UDB with no parameters: udb
  2) load the recording lazily: loadlazy <recording file>
  3) to populate a backtrace that is showing no symbols: popbt
  4) to try and load the relevant symbols given a name: loadsymlib <string>

NOTE: loadsymlib is slow and it doe not guarantee good results as yet.
