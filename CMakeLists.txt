cmake_minimum_required(VERSION 3.14)
project(temporis VERSION 0.1.0 LANGUAGES CXX)

# ---- Settings ----
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---- Options ----
option(BUILD_TESTS "Build tests" ON)

find_package(nlohmann_json REQUIRED)


# ---- Include dirs ----
include_directories(${PROJECT_SOURCE_DIR}/include)

# ---- Library ----
add_library(temporis
    src/RegimeLatencyModel.cpp
    src/QueueLatencyModel.cpp
    src/NetworkSimulator.cpp
    src/Random.cpp
    src/ExperimentParams.cpp
    src/ZenohQueueModel.cpp
)

target_include_directories(temporis
    PUBLIC ${PROJECT_SOURCE_DIR}/include
    PUBLIC ${PROJECT_SOURCE_DIR}/include/latency
    PUBLIC ${PROJECT_SOURCE_DIR}/include/core
)

# ---- Compiler warnings ----
if (MSVC)
    target_compile_options(temporis PRIVATE /W4)
else()
    target_compile_options(temporis PRIVATE -Wall -Wextra -Wpedantic)
endif()

# ---- Example ----
add_executable(consensus_demo
    examples/consensus_demo.cpp
)

target_link_libraries(consensus_demo temporis)
target_link_libraries(temporis PRIVATE nlohmann_json::nlohmann_json)

# ---- Tests ----
if(BUILD_TESTS)
    enable_testing()

    add_executable(test_latency
        tests/test_latency.cpp
    )

    target_link_libraries(test_latency temporis)

    add_test(NAME LatencyTests COMMAND test_latency)
endif()