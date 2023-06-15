cmake_minimum_required(VERSION 3.14)
project(basic_undo_gtest_annotation)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(
  googletest
  URL https://github.com/google/googletest/archive/23f642ab2317c632d93326c65efd44671c1d9985.zip
)

FetchContent_MakeAvailable(googletest)

enable_testing()

add_executable(
  listener_test
)

find_library(
  UNDOEX_LIBRARY
  NAMES libundoex_pic_x64.a
)

find_path(
  UNDOEX_INCLUDE
  NAMES undoex-test-annotations.h
)

target_include_directories(
  listener_test
  PRIVATE
  "../"
  "${UNDOEX_INCLUDE}"
)

target_sources(
  listener_test
  PRIVATE listener_test.cc
)

target_link_libraries(
  listener_test
  GTest::gtest
  "${UNDOEX_LIBRARY}"
)

include(GoogleTest)
gtest_discover_tests(listener_test)
