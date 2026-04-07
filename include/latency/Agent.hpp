#pragma once
#include <iostream>
#include <math.h>

class Agent {
public:
    int id;
    double state =0.0;
    double alpha ;
    double degree; //N-1
    bool validation_check;
    std::vector<double> latency_trace; //tunning

    enum class WeightMode {
        CONSTANT,
        AGE_DECAY
    };

    void step(const std::vector<Message>& inbox, double current_time) {
    double sum = 0.0;
    double last_curr = 0.0;
    double last_ts = 0.0;
    double last_value = 0.0;
    double last_state = 0.0;

     WeightMode mode = validation_check ? WeightMode::CONSTANT : WeightMode::AGE_DECAY;

        auto weight_fn = [mode](double age) {
                switch (mode) {
                    case WeightMode::CONSTANT:
                        return 1.0;
                    case WeightMode::AGE_DECAY:
                        return 1.0 / (1.0 + age);
                }
                return 1.0;
            };
    

        for (auto& m : inbox) {

            double age = current_time - m.timestamp;
            double w = weight_fn(age);

            sum += w * (m.value - state);

            last_curr = current_time;
            last_ts = m.timestamp;
            last_value = m.value;
            last_state = state;

        }

        double delta = alpha * sum / degree;

        /*if(id == 0){
            std::cout << "[DEBUG] alpha " << alpha << std::endl;
            std::cout << "[DEBUG] sum " << sum << std::endl;
            std::cout << "[DEBUG] degree " << degree << std::endl;
             std::cout << "[DEBUG] vlaue " << last_value << " state " << last_state<< std::endl;
             std::cout << "[DEBUG] curr ts " << last_curr << " ts " << last_ts << std::endl;
            if (fabs(delta) < 1e-12) {
                std::cout << "[DEBUG] delta ~ 0" << std::endl;
            } else {
                std::cout << "[DEBUG] delta = " << delta << std::endl;
            }
        }*/

        state += delta;
       /* if(id == 0){
            std::cout << "[DEBUG] state after " << state << std::endl;
         }*/
        sum = 0.0;
            }
};