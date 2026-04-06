#pragma once
#include <vector>
#include "Message.hpp"
#include "LatencyModel.hpp"

#include <queue>

struct CompareDeliveryTime {
    bool operator()(const Message& a, const Message& b) {
        return a.delivery_time > b.delivery_time;
    }
};



class NetworkSimulator {
public:
    NetworkSimulator(LatencyModel* model, int num_agents);

    int send(Message msg,  double current_time);

    void tick(double current_time);

    void get_latency_stats(double& mean, double& var);

    int queue_size() const {
        return std::min((int)buffer_.size(), 1000);
    }

    std::vector<Message> receive(int agent_id);

private:
    LatencyModel* model_;
    std::vector<std::vector<Message>> inboxes_;
    std::priority_queue<Message, std::vector<Message>, CompareDeliveryTime> buffer_;
    double current_time_ = 0.0;
    double latency_sum_ = 0.0;
    double latency_sq_sum_ = 0.0;
    int latency_count_ = 0;
};