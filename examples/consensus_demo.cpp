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

    double dt = 0.1;  
    double time = 0.0;

    for (int i = 0; i < config.N; i++) {
        agents[i].id = i;
        agents[i].state = rand() % 100;
        agents[i].degree = config.N-1;
        agents[i].alpha = config.alpha;
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
                
                net.send(m, time);
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

            // network
            double mean_lat, var_lat;
            net.get_latency_stats(mean_lat, var_lat);

            logger.log_network(t, mean_lat, var_lat, net.queue_size());

            // console
            if (t % 50 == 0) {
                std::cout << "t=" << time
                        << " avg=" << avg
                        << " var=" << var
                        << std::endl;
            }
    }
}