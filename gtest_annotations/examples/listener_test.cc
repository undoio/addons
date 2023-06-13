#include <gtest/gtest.h>

#include "undo_gtest_annotation.h"

TEST(BasicTest, Equality)
{
    EXPECT_EQ(1, 1);
    EXPECT_TRUE(1 == 1);
}

TEST(BasicTest, Addition)
{
    EXPECT_TRUE(1 + 1 == 2);
}

TEST(BasicTest, Fails)
{
    EXPECT_TRUE(1 == 2);
}

GTEST_API_ int
main(int argc, char **argv)
{
    testing::InitGoogleTest(&argc, argv);

    testing::UnitTest::GetInstance()->listeners().Append(new undo_annotation::UndoAnnotationListener);
    return RUN_ALL_TESTS();
}
