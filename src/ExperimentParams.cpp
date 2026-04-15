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
    if (s == "NAIVE_CORRELATED") return RegimeLatencyModel::Mode::NAIVE_CORRELATED;
    if (s == "CORRELATED") return RegimeLatencyModel::Mode::CORRELATED;
    if (s == "REGIME_CORRELATED") return RegimeLatencyModel::Mode::REGIME_CORRELATED;
    if (s == "QUEUE") return RegimeLatencyModel::Mode::QUEUE;

    throw std::runtime_error("Unknown mode: " + s);
}

ExperimentConfig load_config(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) {
        throw std::runtime_error("Cannot open config file");
    }
    json j;
    f >> j;

    ExperimentConfig config;

    auto je = j["experiment"];
    config.N = je.value("N", 50);
    config.steps = je.value("steps", 1000);
    config.alpha = je.value("alpha", 0.1);
    config.dt = je.value("dt", 0.1);
    config.mode = parse_mode(je.value("mode", "NO_DELAY"));
    config.validation_check = je.value("validation_check", false);
    config.seed = je.value("seed", static_cast<uint64_t>(2));

    auto jl = j["latency"];

    config.latency.normal_mean = jl.value("normal_mean", 2.0);
    config.latency.congested_mean = jl.value("congested_mean", 30.0);

    config.latency.normal_std = jl.value("normal_std", 2.0);
    config.latency.congested_std = jl.value("congested_std", 20.0);

    config.latency.congestion_threshold = jl.value("congestion_threshold", 100.0);

    // Backward-compat: accept either innovation_std (new) or noise_std (old).
    if (jl.contains("innovation_std")) {
        config.latency.innovation_std = jl.value("innovation_std", 5.0);
    } else {
        config.latency.innovation_std = jl.value("noise_std", 5.0);
    }
    config.latency.rho = jl.value("rho", 0.8);

    config.latency.base_delay = jl.value("base_delay", 2.0);
    config.latency.bandwidth = jl.value("bandwidth", 50.0);
    config.latency.packet_size = jl.value("packet_size", 255.0);

    // REGIME_CORRELATED-specific. Defaults chosen so that if you forget to
    // set them you still get a sane NORMAL-regime log-AR(1) process.
    config.latency.normal_innovation_std =
        jl.value("normal_innovation_std", config.latency.innovation_std);
    config.latency.congested_innovation_std =
        jl.value("congested_innovation_std", config.latency.innovation_std);
    config.latency.p_normal_to_congested = jl.value("p_normal_to_congested", 0.001);
    config.latency.p_congested_to_normal = jl.value("p_congested_to_normal", 0.05);


    config.latency.propagation_delay = jl.value("propagation_delay", 0.0);
    return config;
}

void print_config(const ExperimentConfig& config) {
    std::cout << "=== EXPERIMENT CONFIG ===\n";

    std::cout << "N: " << config.N << "\n";
    std::cout << "steps: " << config.steps << "\n";
    std::cout << "alpha: " << config.alpha << "\n";
    std::cout << "dt: " << config.dt << "\n";
    std::cout << "validation_check: " << config.validation_check << "\n";
    std::cout << "seed: " << config.seed << "\n";

    std::cout << "mode: ";
    switch (config.mode) {
        case RegimeLatencyModel::Mode::NO_DELAY: std::cout << "NO_DELAY\n"; break;
        case RegimeLatencyModel::Mode::IID: std::cout << "IID\n"; break;
        case RegimeLatencyModel::Mode::IID_EXPONENTIAL: std::cout << "IID_EXPONENTIAL\n"; break;
        case RegimeLatencyModel::Mode::REGIME: std::cout << "REGIME\n"; break;
        case RegimeLatencyModel::Mode::NAIVE_CORRELATED: std::cout << "NAIVE_CORRELATED\n"; break;
        case RegimeLatencyModel::Mode::CORRELATED: std::cout << "CORRELATED\n"; break;
        case RegimeLatencyModel::Mode::REGIME_CORRELATED: std::cout << "REGIME_CORRELATED\n"; break;
        case RegimeLatencyModel::Mode::QUEUE: std::cout << "QUEUE\n"; break;
    }

    std::cout << "--- Latency params ---\n";
    std::cout << "normal_mean: " << config.latency.normal_mean << "\n";
    std::cout << "congested_mean: " << config.latency.congested_mean << "\n";
    std::cout << "normal_std: " << config.latency.normal_std << "\n";
    std::cout << "congested_std: " << config.latency.congested_std << "\n";
    std::cout << "congestion_threshold: " << config.latency.congestion_threshold << "\n";

    std::cout << "innovation_std (sigma_eps): " << config.latency.innovation_std << "\n";
    std::cout << "rho: " << config.latency.rho << "\n";

    std::cout << "base_delay: " << config.latency.base_delay << "\n";
    std::cout << "bandwidth: " << config.latency.bandwidth << "\n";
    std::cout << "packet_size: " << config.latency.packet_size << "\n";

    std::cout << "--- REGIME_CORRELATED params ---\n";
    std::cout << "normal_innovation_std: " << config.latency.normal_innovation_std << "\n";
    std::cout << "congested_innovation_std: " << config.latency.congested_innovation_std << "\n";
    std::cout << "p_normal_to_congested: " << config.latency.p_normal_to_congested << "\n";
    std::cout << "p_congested_to_normal: " << config.latency.p_congested_to_normal << "\n";
    std::cout << "propagation_delay: " << config.latency.propagation_delay << "\n";

    std::cout << "result path: " << config.results_dir << "\n";
    std::cout << "========================\n";
}