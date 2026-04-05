#include <stdio.h>
#include <RegimeLatencyModel.hpp>
#include <NetworkSimulator.hpp>
#include <Agent.hpp>
#include <Message.hpp>
#include <random>
#include <cmath>
#include <chrono>
#include <iostream>


int main() {
    const int N = 50;
    RegimeLatencyModel latency_model(RegimeLatencyModel::Mode::REGIME);
    NetworkSimulator net(&latency_model,N);
    std::vector<Agent> agents(N);

  //  std::bernoulli_distribution update_prob(0.1);
  //  static std::mt19937 rng(42);

    for (int i = 0; i < N; i++) {
        agents[i].id = i;
        agents[i].state = rand() % 100;
        agents[i].degree = N-1;
    }
    double avg0 = 0;
    for (auto& a : agents) avg0 += a.state;
    avg0 /= N;

    std::cout << "initial avg = " << avg0 <<std::endl;


    for (int t = 0; t < 1000; t++) {

        int load = N * N;

        // send all-to-all
        for (auto& a : agents) {
            for (auto& b : agents) {
                if(a.id == b.id) continue;
                Message m;
                m.sender = a.id;
                m.receiver = b.id;
                m.value = a.state;
                
                net.send(m, load, t);
            }
        }

        if (t % 50 == 0) {
            double avg = 0;
            double var = 0;

            for (auto& a : agents) avg += a.state;
            avg /= N;

            for (auto& a : agents) var += (a.state - avg) * (a.state - avg);
            var /= N;

            std::cout << "t=" << t 
                    << " avg=" << avg 
                    << " var=" << var 
                    << std::endl;
        }

        net.tick(t);


        for (int i = 0; i < N; i++) {
            auto inbox = net.receive(i);
            
            //std::cout << "inbox size: " << inbox.size() << std::endl;
           // std::cout << inbox.size() << std::endl; 
           //if(update_prob(rng)) agents[i].step(inbox);
           agents[i].step(inbox);
        }
    }
}