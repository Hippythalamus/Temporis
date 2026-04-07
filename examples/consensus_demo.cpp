#include <stdio.h>
#include <RegimeLatencyModel.hpp>
#include <NetworkSimulator.hpp>
#include <ExperimentParams.hpp>
#include <Agent.hpp>
#include <Message.hpp>
#include <random>
#include <cmath>
#include <chrono>
#include <iostream>

double compute_acf_lag1(const std::vector<double>& x);
std::vector<int> compute_bursts(const std::vector<double>& trace, double threshold);

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: ./consensus_demo <config_path>\n";
        return 1;
    }

    std::string config_path = argv[1];

    auto config = load_config(config_path);

    ExperimentLogger logger(config_path);
    config.results_dir = logger.results_dir();

    print_config(config);

    RegimeLatencyModel latency_model(config.mode, config.latency);
    NetworkSimulator net(&latency_model, config.N);
    std::vector<Agent> agents(config.N);
    std::map<std::pair<int,int>, std::vector<double>> latency_traces; //analize 
    std::vector<double> global_latency_trace; //analize 
    

    double dt = 0.1;  
    double time = 0.0;
    static double prev_var = 1e18;

    for (int i = 0; i < config.N; i++) {
        agents[i].id = i;
        agents[i].state = rand() % 100;
        agents[i].degree = config.N-1;
        agents[i].alpha = config.alpha;
        agents[i].validation_check = config.validation_check;
    }
    double avg0 = 0;
    for (auto& a : agents) avg0 += a.state;
    avg0 /= config.N;

    std::cout << "initial avg = " << avg0 <<std::endl;


    for (int t = 0; t < config.steps; t++) {
        
        time += dt;
        // send all-to-all
        for (auto& a : agents) {
            for (auto& b : agents) {
                if(a.id == b.id) continue;
                Message m;
                m.sender = a.id;
                m.receiver = b.id;
                m.value = a.state;
                double delay = net.send(m, time);

                auto key = std::make_pair(a.id, b.id);
                latency_traces[key].push_back(delay);
                global_latency_trace.push_back(delay);
                logger.log_latency(m.delivery_time, a.id, b.id, delay);
            }
        }
        
        net.tick(time);



        for (int i = 0; i < config.N; i++) {
            auto inbox = net.receive(i);
            if (t == 0 && i == 0) {
                std::cout << "inbox size: " << inbox.size() << std::endl;
            }
            
            //std::cout << "inbox size: " << inbox.size() << std::endl;
           // std::cout << inbox.size() << std::endl; 
           //if(update_prob(rng)) agents[i].step(inbox);
           agents[i].step(inbox, time);
        }
        
        double avg = 0, var = 0;

            for (auto& a : agents) avg += a.state;
            avg /= config.N;

            for (auto& a : agents) var += (a.state - avg)*(a.state - avg);
            var /= config.N;

            // system
            logger.log_system(time, avg, var);

           

            if (config.mode == RegimeLatencyModel::Mode::NO_DELAY) {
                if (var > prev_var + 1e-9) {
                    std::cerr << "[ERROR] Variance increased in NO_DELAY at t=" << t << std::endl;
                    exit(1);
                }
                prev_var = var;
            }

            // network
            double mean_lat, var_lat;
            net.get_latency_stats(mean_lat, var_lat);

            logger.log_network(t, mean_lat, var_lat, net.queue_size());

            // console
            if (t % 50 == 0) {
                logger.flush_latency();
                std::cout << "t=" << time
                        << " avg=" << avg
                        << " var=" << var
                        << std::endl;
            }
            if (t % 100 == 0) {
                std::cout << "[LATENCY CHECK] mean=" << mean_lat << std::endl;
            }
    }

        if (config.mode == RegimeLatencyModel::Mode::CORRELATED) {
            double total_acf = 0.0;
            int count = 0;

            for (auto& [key, trace] : latency_traces) {
                double acf = compute_acf_lag1(trace);
                if (acf == 0.0) continue;

                total_acf += acf;
                count++;
            }

            double mean_acf = (count > 0) ? total_acf / count : 0.0;

            std::cout << "[ACF lag1 per-link avg] " << mean_acf << std::endl;
            logger.log_metric("acf_lag1_per_link", mean_acf);
        }
        if (config.mode == RegimeLatencyModel::Mode::IID) {
            double acf = compute_acf_lag1(global_latency_trace);

            std::cout << "[ACF IID global] " << acf << std::endl;
            logger.log_metric("acf_global", acf);
        }
        if (config.mode == RegimeLatencyModel::Mode::REGIME) {
            double acf = compute_acf_lag1(global_latency_trace);

            std::cout << "[ACF REGIME global] " << acf << std::endl;
            logger.log_metric("acf_global", acf);

            auto bursts = compute_bursts(global_latency_trace, config.latency.normal_mean);

            double avg_burst = 0;
            for (int b : bursts) avg_burst += b;
            avg_burst /= bursts.size();

            std::cout << "[REGIME burst avg] " << avg_burst << std::endl;
            logger.log_metric("burst_avg", avg_burst);
        }
    }


    double compute_acf_lag1(const std::vector<double>& x) {
        int n = x.size();
        if (n < 50) return 0.0;

        int start = std::min(100, n / 10); // burn-in

        double mean = 0.0;
        int count = 0;

        for (int i = start; i < n; i++) {
            mean += x[i];
            count++;
        }
        mean /= count;

        double num = 0.0, den = 0.0;

        for (int i = start + 1; i < n; i++) {
            num += (x[i] - mean) * (x[i-1] - mean);
        }

        for (int i = start; i < n; i++) {
            den += (x[i] - mean)*(x[i] - mean);
        }

        if (den < 1e-12) return 0.0;

        return num / den;
    }

    std::vector<int> compute_bursts(const std::vector<double>& trace, double threshold) {
        std::vector<int> bursts;
        int current = 0;

        for (double v : trace) {
            if (v > threshold) {
                current++;
            } else {
                if (current > 0) bursts.push_back(current);
                current = 0;
            }
        }

        if (current > 0) bursts.push_back(current);

        return bursts;
    }