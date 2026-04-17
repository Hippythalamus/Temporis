#pragma once

#include <vector>
#include <LatencyModel.hpp>

/**
 * QueueLatencyModel — mechanistic latency model based on shared sender-side
* M/D/1 queues.
*
* Step 1 of the queue-based model implementation. Implements the minimal
* configuration described in docs/queue_model.md:
*   - shared sender-side queue placement (one queue per sender, used for
*     all outgoing destinations)
*   - constant bandwidth (no bandwidth_logstd, no bandwidth_rho)
*   - no service noise (service_noise_logstd = 0)
*   - unbounded queue capacity (no drops)
*
* Each sender i is treated as an M/D/1 queue:
*   - all messages from i, regardless of destination, go through the same queue
*   - service time is deterministic: packet_size / bandwidth
*   - the queue is fully described by a single scalar `t_complete` per sender
*     (the time at which the queue will next be free), so no deque is needed
*
* This shared-sender placement is appropriate for senders that have one
* effective upstream channel (a robot's WiFi radio, a process's DDS write
* path + OS socket buffer, etc.). For Zenoh-specific topologies (peer mode
* per-link, client+router, mesh) see docs/queue_model.md §11 and the
* planned Etap 4 work; this version is intentionally generic.
*
* The receiver argument is accepted by compute_delay() for interface
* compatibility with LatencyModel::sample, but is not used by queue
* dynamics — only the sender's queue is tracked.
 *
 * Tie-breaking on simultaneous arrivals
 * --------------------------------------
 * In consensus_demo, all agents send at every simulation step, which would
 * otherwise produce identical t_arrival for many messages and leave their
 * order in the queue determined by C++ iteration order — physically
 * meaningless and a source of silent reproducibility issues.
 *
 * The model resolves this by adding a tiny deterministic offset based on
 * sender id inside compute_delay():
 *
 *     t_real = t_arrival + sender_id * TIE_BREAK_EPS
 *
 * where TIE_BREAK_EPS = 1e-9 seconds. This is purely a **tie-breaking
 * artifact for queue accounting**, not physical time. The offset is at
 * least six orders of magnitude smaller than any physically meaningful
 * latency scale in the model (typical service times are >= 1e-5 seconds,
 * propagation delays are >= 1e-3 seconds), so it does not appear in any
 * downstream statistics — marginal distribution, percentiles, ACF, or
 * burst structure. It exists solely to make the order in which
 * simultaneously-arriving messages enter the queue reproducible across
 * runs and independent of compiler / container behavior.
 *
 * The earlier alternative — scaling the offset by dt/num_agents — was
 * rejected because it introduces a fictitious deterministic temporal
 * structure (sender 49 always 20 ms behind sender 0 at dt=1, num=50),
 * which can create spurious autocorrelation and even resonate with the
 * physical service time scale. See docs/queue_model.md §4.
 *
 * Note on time semantics
 * ----------------------
 * Because of the tie-break offset, `t_arrival` as passed by the caller
 * is **not** the physical time at which the message enters the queue.
 * The physical (model-internal) time is `t_real = t_arrival + offset`.
 * All queue dynamics — service start, completion, accumulated backlog —
 * live in `t_real` coordinates. The returned delay is measured in the
 * `t_real` frame so that the tie-break offset cancels out and does not
 * appear in observed latency. When analysing simulator traces, treat
 * `t` in latency.csv as the simulator's coarse send time (the caller's
 * `t_arrival`), not as the queue's internal physical time.
 */


class QueueLatencyModel : public LatencyModel{
public:
    struct Config {
        // Required physical parameters
        double bandwidth;          // bytes per second
        double propagation_delay;  // seconds
        double packet_size;        // bytes per message

        // Required for sizing the link state matrix
        int    num_agents;         // total number of agents in the experiment
    };

    explicit QueueLatencyModel(const Config& config);

    double sample(int sender, int receiver, double t,
                  int network_load, int queue_size) override;

    /**
     * Compute the end-to-end delay for one message.
     *
     * @param sender     id of the sending agent (0 <= sender < num_agents)
     * @param receiver   id of the receiving agent (0 <= receiver < num_agents)
     * @param t_arrival  the arrival time at the queue, the simulator's
     *                   current time. Same time may be passed for multiple
     *                   messages within one simulation step; the model
     *                   applies a tiny deterministic tie-break by sender id
     *                   to make queue accounting reproducible.
     *
     * @return  end-to-end delay in seconds: queueing + serialization +
     *          propagation. This is the value to be added to t_arrival
     *          to obtain the delivery time, and the value that should
     *          appear in latency.csv as the `delay` column.
     *
     * Side effect: updates the internal t_complete for sender's queue.
     * The receiver argument does not affect queue state.
     */
    double compute_delay(int sender, int receiver, double t_arrival);

    /**
     * Reset all sender queue states to t_complete = 0.
     *
     * Intended for starting a fresh experiment. Not designed for
     * mid-simulation reset (where you might want t_complete = current_time
     * to mark queues as "empty as of now"); that is out of scope.
     */
    void reset();

private:
    // Tie-breaking epsilon for simultaneous arrivals (see header comment).
    // Chosen large enough to remain meaningful at double precision for
    // simulation times up to ~1e6 seconds, and small enough to be many
    // orders of magnitude below any physical latency scale.
    static constexpr double TIE_BREAK_EPS = 1e-9;

    struct SenderState {
        double t_complete = 0.0;  // time at which this sender's queue is next free
    };

    // One queue per sender. All outgoing messages from sender i, regardless
    // of destination, share the same queue and compete for the same
    // serialization bandwidth. This models a single shared upstream channel
    // (robot's radio, DDS write path, etc.).
    std::vector<SenderState> senders_;

    double service_time_;       // = packet_size / bandwidth, precomputed
    double propagation_delay_;
};