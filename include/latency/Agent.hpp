#pragma once
#include <iostream>
#include <math.h>
#include <vector>
#include "Message.hpp"

class Agent {
public:
    int id;
    double state = 0.0;
    double alpha;
    double degree; // N-1 for all-to-all
    // If true: weight messages as 1/(1+age) (penalize stale messages).
    // If false: constant weights (the canonical consensus weighting,
    // useful as a validation baseline because it makes the average a
    // strict invariant under NO_DELAY).
    bool use_age_decay_weights = true;
    std::vector<double> latency_trace;

    void step(const std::vector<Message>& inbox, double current_time) {
        double sum = 0.0;

        auto weight_fn = [this](double age) {
            if (use_age_decay_weights) {
                return 1.0 / (1.0 + age);
            }
            return 1.0;
        };

        for (auto& m : inbox) {
            double age = current_time - m.timestamp;
            double w = weight_fn(age);
            sum += w * (m.value - state);
        }

        double delta = alpha * sum / degree;
        state += delta;
    }
};