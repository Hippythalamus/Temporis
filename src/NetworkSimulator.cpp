#include "NetworkSimulator.hpp"



NetworkSimulator::NetworkSimulator(LatencyModel* model, int num_agents)
    : model_(model), inboxes_(num_agents)
{}

int NetworkSimulator::send(Message msg, int load, double current_time)
{
    double delay = model_->sample(msg.sender, msg.receiver, current_time, load);

    msg.timestamp = current_time;
    msg.delivery_time = current_time + delay;

    if(msg.delivery_time < current_time)  return -1;

    buffer_.push(msg);
    return 0;
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