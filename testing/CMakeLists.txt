project(testing VERSION 0.1.0 LANGUAGES CXX)

add_executable(testing main.cpp)
target_link_libraries(testing PUBLIC SDL++)
