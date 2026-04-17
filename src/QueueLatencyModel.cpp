#include "QueueLatencyModel.hpp"

#include <algorithm>   // std::max
#include <cassert>     // assert
#include <stdexcept>   // std::invalid_argument
#include <string>

QueueLatencyModel::QueueLatencyModel(const Config& config)
    : senders_(),  // sized below after validation
      service_time_(0.0),
      propagation_delay_(config.propagation_delay)
{
    // Validate config. Fail fast with a clear message rather than
    // silently producing nonsensical results (negative service time,
    // empty link matrix, division by zero, etc.).
    if (config.bandwidth <= 0.0) {
        throw std::invalid_argument(
            "QueueLatencyModel: bandwidth must be > 0 (got " +
            std::to_string(config.bandwidth) + ")");
    }
    if (config.packet_size <= 0.0) {
        throw std::invalid_argument(
            "QueueLatencyModel: packet_size must be > 0 (got " +
            std::to_string(config.packet_size) + ")");
    }
    if (config.propagation_delay < 0.0) {
        throw std::invalid_argument(
            "QueueLatencyModel: propagation_delay must be >= 0 (got " +
            std::to_string(config.propagation_delay) + ")");
    }
    if (config.num_agents <= 0) {
        throw std::invalid_argument(
            "QueueLatencyModel: num_agents must be > 0 (got " +
            std::to_string(config.num_agents) + ")");
    }

    service_time_ = config.packet_size / config.bandwidth;

    // Allocate one queue per sender. Each SenderState is default-constructed
    // with t_complete = 0.
    senders_.assign(config.num_agents, SenderState{});
}

double QueueLatencyModel::compute_delay(int sender, int receiver,
                                        double t_arrival)
{
    // Bounds checks: only sender matters for queue state. Receiver is
    // accepted for interface compatibility but does not index into queue
    // storage in the shared-sender placement.
    assert(sender   >= 0 && sender   < static_cast<int>(senders_.size()));
    assert(receiver >= 0 && receiver < static_cast<int>(senders_.size()));

    // Self-loops are not part of the model.
    assert(sender != receiver);

    // Tie-break: ensure simultaneously-arriving messages enter the queue
    // in a reproducible order independent of caller iteration order.
    const double t_real = t_arrival + sender * TIE_BREAK_EPS;

    // Floating-point collapse guard.
    assert(sender == 0 || t_real != t_arrival);

    SenderState& sender_q = senders_[sender];

    // M/D/1 recursion: a new message starts service either immediately
    // (queue empty) or when the previous message finishes (queue busy).
    // Note that consecutive messages from the same sender to *different*
    // receivers still queue behind each other — that is the whole point
    // of shared sender-side placement.
    const double t_start    = std::max(t_real, sender_q.t_complete);
    const double t_complete = t_start + service_time_;

    sender_q.t_complete = t_complete;

    // End-to-end delay = queueing + serialization + propagation.
    return (t_complete - t_real) + propagation_delay_;
}

double QueueLatencyModel::sample(int sender, int receiver, double t,
                                  int /*network_load*/, int /*queue_size*/)
{
    return compute_delay(sender, receiver, t);
}

void QueueLatencyModel::reset()
{
    for (auto& sender_q : senders_) {
        sender_q.t_complete = 0.0;
    }
}
