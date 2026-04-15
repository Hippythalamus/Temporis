#include "QueueLatencyModel.hpp"

#include <algorithm>   // std::max
#include <cassert>     // assert
#include <stdexcept>   // std::invalid_argument
#include <string>

QueueLatencyModel::QueueLatencyModel(const Config& config)
    : links_(),  // sized below after validation
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

    // Allocate dense [num_agents][num_agents] link state matrix.
    // Each LinkState is default-constructed with t_complete = 0.
    links_.assign(config.num_agents,
                  std::vector<LinkState>(config.num_agents));
}

double QueueLatencyModel::compute_delay(int sender, int receiver,
                                        double t_arrival)
{
    // Bounds checks: out-of-range indices would otherwise be silent UB
    // (segfault if lucky, garbage read if not). Use assert so these
    // disappear with -DNDEBUG in release builds; compute_delay is on
    // the hot path, called once per message.
    assert(sender   >= 0 && sender   < static_cast<int>(links_.size()));
    assert(receiver >= 0 && receiver < static_cast<int>(links_.size()));

    // Self-loops are not part of the model: agents do not send to
    // themselves in any current Temporis experiment. If a future caller
    // legitimately needs self-loops, replace this assert with explicit
    // handling.
    assert(sender != receiver);

    // Tie-break: ensure simultaneously-arriving messages enter the queue
    // in a reproducible order independent of caller iteration order.
    // See header comment and docs/queue_model.md §4 for rationale.
    const double t_real = t_arrival + sender * TIE_BREAK_EPS;

    // Floating-point collapse guard: at very large t_arrival (~1e9 s and
    // up), double precision is ~1e-7, which would silently swallow our
    // 1e-9 epsilon and break tie-breaking. Catch this in debug builds.
    // Not a problem at any realistic Temporis simulation length, but
    // worth flagging if it ever happens.
    assert(sender == 0 || t_real != t_arrival);

    LinkState& link = links_[sender][receiver];

    // M/D/1 recursion: a new message starts service either immediately
    // (queue is empty) or when the previous message finishes (queue is busy).
    const double t_start    = std::max(t_real, link.t_complete);
    const double t_complete = t_start + service_time_;

    link.t_complete = t_complete;

    // End-to-end delay = queueing + serialization + propagation.
    // Measured from t_real (the effective arrival used for queue accounting),
    // not from the raw t_arrival, so the tie-break offset cancels out and
    // does not contaminate observed latency.
    return (t_complete - t_real) + propagation_delay_;
}

double QueueLatencyModel::sample(int sender, int receiver, double t,
                                  int /*network_load*/, int /*queue_size*/)
{
    return compute_delay(sender, receiver, t);
}

void QueueLatencyModel::reset()
{
    for (auto& row : links_) {
        for (auto& link : row) {
            link.t_complete = 0.0;
        }
    }
}
