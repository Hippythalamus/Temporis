#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <chrono>
#include "ExperimentParams.hpp"
#include <filesystem>

using json = nlohmann::json;

RegimeLatencyModel::Mode parse_mode(const std::string& s) {
    if (s == "NO_DELAY") return RegimeLatencyModel::Mode::NO_DELAY;
    if (s == "IID") return RegimeLatencyModel::Mode::IID;
    if (s == "IID_EXPONENTIAL") return RegimeLatencyModel::Mode::IID_EXPONENTIAL;
    if (s == "REGIME") return RegimeLatencyModel::Mode::REGIME;
    if (s == "CORRELATED") return RegimeLatencyModel::Mode::CORRELATED;

    throw std::runtime_error("Unknown mode: " + s);
}

ExperimentConfig load_config(const std::string& path) {
    std::ifstream f(path);
    if(!f.is_open()){
        throw std::runtime_error("Cannot open config file");
    }
    json j;
    f >> j;

    ExperimentConfig config;

    // experiment
    auto je = j["experiment"];
    config.N = je.value("N", 50);
    config.steps = je.value("steps", 1000);
    config.alpha = je.value("alpha", 0.1);

    config.mode = parse_mode(je.value("mode", "NO_DELAY"));

    config.validation_check = je.value("validation_check", false);

    // latency
    auto jl = j["latency"];

    config.latency.normal_mean = jl.value("normal_mean", 2.0);
    config.latency.congested_mean = jl.value("congested_mean", 30.0);

    config.latency.normal_std = jl.value("normal_std", 2.0);
    config.latency.congested_std = jl.value("congested_std", 20.0);

    config.latency.congestion_threshold = jl.value("congestion_threshold", 100.0);

    config.latency.noise_std = jl.value("noise_std", 5.0);
    config.latency.rho = jl.value("rho", 0.8);

    config.latency.base_delay = jl.value("base_delay", 2.0);
    config.latency.bandwidth = jl.value("bandwidth", 50.0);
    config.latency.packet_size = jl.value("packet_size", 255.0);
    

    return config;
}

void print_config(const ExperimentConfig& config) {
    std::cout << "=== EXPERIMENT CONFIG ===\n";

    std::cout << "N: " << config.N << "\n";
    std::cout << "steps: " << config.steps << "\n";
    std::cout << "alpha: " << config.alpha << "\n";
    std::cout << "validation_check: " << config.validation_check << "\n";

    std::cout << "mode: ";
    switch (config.mode) {
        case RegimeLatencyModel::Mode::NO_DELAY: std::cout << "NO_DELAY\n"; break;
        case RegimeLatencyModel::Mode::IID: std::cout << "IID\n"; break;
        case RegimeLatencyModel::Mode::IID_EXPONENTIAL: std::cout << "IID_EXPONENTIAL\n"; break;
        case RegimeLatencyModel::Mode::REGIME: std::cout << "REGIME\n"; break;
        case RegimeLatencyModel::Mode::CORRELATED: std::cout << "CORRELATED\n"; break;
    }

    std::cout << "--- Latency params ---\n";
    std::cout << "normal_mean: " << config.latency.normal_mean << "\n";
    std::cout << "congested_mean: " << config.latency.congested_mean << "\n";
    std::cout << "normal_std: " << config.latency.normal_std << "\n";
    std::cout << "congested_std: " << config.latency.congested_std << "\n";
    std::cout << "congestion_threshold: " << config.latency.congestion_threshold << "\n";

    std::cout << "noise_std: " << config.latency.noise_std << "\n";
    std::cout << "rho: " << config.latency.rho << "\n";

    std::cout << "base_delay: " << config.latency.base_delay << "\n";
    std::cout << "bandwidth: " << config.latency.bandwidth << "\n";

    std::cout << "packet size: " << config.latency.packet_size << "\n";

    std::cout << "result path: " << config.results_dir << "\n";


    std::cout << "========================\n";
}
