# Google Test annotations

## Overview

This provides a listener for [Google Test](https://github.com/google/googletest)
to insert annotations in recordings made with LiveRecorder or UDB.

If your Google Test integration already has a `main` function, enabling this
should just require the following:
- `#include <undo_gtest_annotation.h>` before `main`.
- in main, call:
  ```c++
  testing::UnitTest::GetInstance()->listeners().Append(new undo_annotation::UndoAnnotationListener);
  ```

If you don't already have a `main` function, you'll need to add one. The most
basic version is:
```c++
GTEST_API_ int
main(int argc, char **argv)
{
    testing::InitGoogleTest(&argc, argv);

    testing::UnitTest::GetInstance()->listeners().Append(new undo_annotation::UndoAnnotationListener);
    return RUN_ALL_TESTS();
}
```

The header file includes `undoex-test-annotations.h`, which is included in the
`undoex` path of a UDB release. It also requires the library to be included in
the build - it is distributed for both static and dynamic linking.

## Limitations

Note that the annotations are inserted at the point in time in the plugin, so
when going to the start of a test you will need to step forward to find the
actual start of a test. Likewise, when going to the end of a test you will need
to step backward.
