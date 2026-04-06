#pragma once
#include "latency/LatencyModelParams.hpp"
#include "latency/RegimeLatencyModel.hpp"
#include <iostream>
#include <chrono>
#include <fstream>
#include <filesystem>

struct ExperimentConfig {
public:
    int N;
    int steps;
    double alpha;

    RegimeLatencyModel::Mode mode;
    RegimeLatencyModel::Regime regime;

    LatencyParams latency;
    std::string results_dir;
};

ExperimentConfig load_config(const std::string& path);
void print_config(const ExperimentConfig& config);

namespace fs = std::filesystem;

class ExperimentLogger {
public:
    ExperimentLogger(const std::string& config_path) {
        setup_results_dir();
        copy_config(config_path);
        open_files();
    }

    void log_system(int t, double avg, double var) {
        system_csv_ << t << "," << avg << "," << var << "\n";
    }

    void log_network(int t, double mean_lat, double var_lat, int queue_size) {
        network_csv_ << t << "," << mean_lat << "," << var_lat << "," << queue_size << "\n";
    }
    

    std::string results_dir() const {
        return results_dir_;
    }

private:
    std::string results_dir_;

    std::ofstream system_csv_;
    std::ofstream network_csv_;


    void setup_results_dir() {
        std::string base = "../results";

        if (!fs::exists(base)) {
            fs::create_directory(base);
        }

        auto ts = std::chrono::system_clock::now().time_since_epoch().count();
        results_dir_ = base + "/run_" + std::to_string(ts);

        fs::create_directory(results_dir_);
    }

    void copy_config(const std::string& config_path) {
        fs::copy_file(
            config_path,
            results_dir_ + "/config.json",
            fs::copy_options::overwrite_existing
        );
    }


    void open_files() {
        system_csv_.open(results_dir_ + "/system.csv");
        network_csv_.open(results_dir_ + "/network.csv");

        if (!system_csv_ || !network_csv_) {
            throw std::runtime_error("Failed to open CSV files");
        }

        system_csv_ << "t,avg,var\n";
        network_csv_ << "t,mean_latency,var_latency,queue_size\n";
    }
};

