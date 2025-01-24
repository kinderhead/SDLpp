add_library(SDL++ INTERFACE)
target_include_directories(SDL++ INTERFACE .)
target_link_libraries(SDL++ INTERFACE SDL3::SDL3)
