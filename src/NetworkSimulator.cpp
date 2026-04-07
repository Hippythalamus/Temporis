#include "NetworkSimulator.hpp"



NetworkSimulator::NetworkSimulator(LatencyModel* model, int num_agents)
    : model_(model), inboxes_(num_agents)
{}

double NetworkSimulator::send(Message& msg, double current_time)
{
    int queue_size = std::min((int)buffer_.size(), 1000);
    int load = buffer_.size();

    double delay = model_->sample(msg.sender, msg.receiver, current_time, load, queue_size);
    //double delay = model_->sample(msg.sender, msg.receiver, current_time, load);

    msg.timestamp = current_time;
    msg.delivery_time = current_time + delay;


    latency_sum_ += delay;
    latency_sq_sum_ += delay * delay;
    latency_count_++;

    if(msg.delivery_time < current_time)  return -1;

    buffer_.push(msg);
    return delay;
}

void NetworkSimulator::tick(double current_time)
{
    current_time_ = current_time;

    while (!buffer_.empty()) {
        const Message& msg = buffer_.top();

        if (msg.delivery_time > current_time_)
            break;

        Message ready = msg;
        buffer_.pop();

        inboxes_[ready.receiver].push_back(ready);
    }
}


std::vector<Message> NetworkSimulator::receive(int agent_id)
{
    auto& inbox = inboxes_[agent_id];

    std::vector<Message> out = inbox;

    inbox.clear();

    return out;
}

void NetworkSimulator::get_latency_stats(double& mean, double& var) {
    if (latency_count_ == 0) {
        mean = 0;
        var = 0;
        return;
    }

    mean = latency_sum_ / latency_count_;
    var = latency_sq_sum_ / latency_count_ - mean * mean;

    latency_sum_ = 0;
    latency_sq_sum_ = 0;
    latency_count_ = 0;
}