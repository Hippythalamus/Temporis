#pragma once


class Agent {
public:
    int id;
    double state =0.0;
    double alpha = 0.01;
    int degree; //N-1

    void step(const std::vector<Message>& inbox) {
        if (inbox.empty()) return;
        double sum = 0.0;
        for (const auto& m : inbox) {
            sum += m.value - state;
        }

        state += alpha * sum/degree;
        
    }
};