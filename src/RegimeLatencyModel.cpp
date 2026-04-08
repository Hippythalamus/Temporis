#include "RegimeLatencyModel.hpp"
#include <random>
#include <cmath>
#include <stdexcept>


RegimeLatencyModel::RegimeLatencyModel(Mode mode, const LatencyParams& p, uint64_t seed)
    : regime_(Regime::NORMAL),
      mode_(mode),

      normal_mean_(p.normal_mean),
      congested_mean_(p.congested_mean),

      normal_std_(p.normal_std),
      congested_std_(p.congested_std),

      congestion_threshold_(p.congestion_threshold),

      innovation_std_(p.innovation_std),
      rho_(p.rho),

      base_delay_(p.base_delay),
      bandwidth_(p.bandwidth),
      packet_size_(p.packet_size),

      normal_innovation_std_(p.normal_innovation_std),
      congested_innovation_std_(p.congested_innovation_std),
      p_normal_to_congested_(p.p_normal_to_congested),
      p_congested_to_normal_(p.p_congested_to_normal),

      rng_(seed)
{}


double RegimeLatencyModel::sample(int sender, int receiver, double t, int load, int queue_size)
{
    switch (mode_) {

        case Mode::NO_DELAY:
            return 0.0;

        case Mode::IID: {
            std::normal_distribution<double> dist(normal_mean_, normal_std_);
            return std::max(0.0, dist(rng_));
        }

        case Mode::IID_EXPONENTIAL: {
            double lambda = 1.0 / normal_mean_;
            std::exponential_distribution<double> dist(lambda);
            return dist(rng_);
        }

        case Mode::REGIME: {
            // Legacy mode: global regime, gaussian, clamped. Kept for
            // comparison only -- don't use for new experiments.
            update_regime(load);

            std::normal_distribution<double> dist(
                regime_ == Regime::NORMAL ? normal_mean_ : congested_mean_,
                regime_ == Regime::NORMAL ? normal_std_ : congested_std_
            );
            return std::max(0.0, dist(rng_));
        }

        case Mode::NAIVE_CORRELATED: {
            // Gaussian AR(1) with hard clamping at 0. Kept as a baseline
            // to show why CORRELATED (log-normal) is necessary when
            // base_delay is small relative to the stationary std.
            //   x_t = base_delay + rho * (x_{t-1} - base_delay) + eps_t
            const double mean = base_delay_;

            auto key = std::make_pair(sender, receiver);
            auto it = prev_linear_state_.find(key);

            double prev;
            if (it == prev_linear_state_.end()) {
                double denom = 1.0 - rho_ * rho_;
                double stationary_std = (denom > 1e-12)
                    ? innovation_std_ / std::sqrt(denom)
                    : innovation_std_;
                std::normal_distribution<double> stat(mean, stationary_std);
                prev = std::max(0.0, stat(rng_));
            } else {
                prev = it->second;
            }

            std::normal_distribution<double> noise(0.0, innovation_std_);
            double latency = mean + rho_ * (prev - mean) + noise(rng_);
            latency = std::max(0.0, latency);

            prev_linear_state_[key] = latency;
            return latency;
        }

        case Mode::CORRELATED: {
            // Pure log-normal AR(1), single regime. Validated baseline.
            //   y_t = log_mean + rho * (y_{t-1} - log_mean) + eps_t
            //   latency = exp(y_t)
            // Calibrated so that E[latency] == base_delay in stationarity:
            //   log_mean = log(base_delay) - 0.5 * stationary_log_std^2
            //
            // Uses ONLY: base_delay, rho, innovation_std.
            // Ignores normal_mean, congested_mean, normal_std, congested_std,
            // and all regime-related params.
            const double denom = 1.0 - rho_ * rho_;
            const double stationary_log_std = (denom > 1e-12)
                ? innovation_std_ / std::sqrt(denom)
                : innovation_std_;
            const double log_mean =
                std::log(base_delay_) - 0.5 * stationary_log_std * stationary_log_std;

            auto key = std::make_pair(sender, receiver);
            LinkState& st = prev_state_[key];

            if (!st.initialized) {
                std::normal_distribution<double> stat(log_mean, stationary_log_std);
                st.log_state = stat(rng_);
                st.initialized = true;
            }

            std::normal_distribution<double> noise(0.0, innovation_std_);
            double new_log =
                log_mean + rho_ * (st.log_state - log_mean) + noise(rng_);

            st.log_state = new_log;
            return std::exp(new_log);
        }

        case Mode::REGIME_CORRELATED: {
            // Markov-switching log-normal AR(1). Per-link regime and state.
            //
            // Two regimes, each a log-normal AR(1):
            //   NORMAL:    log_mean_N, innovation_std = normal_innovation_std
            //   CONGESTED: log_mean_C, innovation_std = congested_innovation_std
            //
            // log_mean for each regime is calibrated so that:
            //   E[latency | regime=NORMAL]    == normal_mean
            //   E[latency | regime=CONGESTED] == congested_mean
            // using the compensation log_mean = log(mean) - 0.5 * stat_log_std^2.
            //
            // Transitions are pure Markov: at each sample, independently,
            // switch with probability p_normal_to_congested or p_congested_to_normal.
            //
            // Important: when switching regimes, we keep log_state as-is.
            // The new regime's AR(1) immediately starts pulling toward the
            // new log_mean. Physically this represents a congestion event
            // that doesn't instantly change the latency but shifts the
            // attractor the process is relaxing toward.
            //
            // Uses: normal_mean, congested_mean, normal_innovation_std,
            //       congested_innovation_std, rho, p_normal_to_congested,
            //       p_congested_to_normal.
            // Ignores: base_delay, innovation_std, normal_std, congested_std.
            const double denom = 1.0 - rho_ * rho_;

            auto log_mean_for = [&](int regime, double inn_std) {
                double stat_log_std = (denom > 1e-12)
                    ? inn_std / std::sqrt(denom)
                    : inn_std;
                double target_mean = (regime == 0) ? normal_mean_ : congested_mean_;
                return std::log(target_mean) - 0.5 * stat_log_std * stat_log_std;
            };

            auto key = std::make_pair(sender, receiver);
            LinkState& st = prev_state_[key];

            if (!st.initialized) {
                // Initialize in NORMAL regime, at its stationary distribution.
                double stat_log_std = (denom > 1e-12)
                    ? normal_innovation_std_ / std::sqrt(denom)
                    : normal_innovation_std_;
                double lm = log_mean_for(0, normal_innovation_std_);
                std::normal_distribution<double> stat(lm, stat_log_std);
                st.log_state = stat(rng_);
                st.regime = 0;
                st.initialized = true;
            }

            // Markov transition, independent of load.
            std::uniform_real_distribution<double> U(0.0, 1.0);
            if (st.regime == 0) {
                if (U(rng_) < p_normal_to_congested_) st.regime = 1;
            } else {
                if (U(rng_) < p_congested_to_normal_) st.regime = 0;
            }

            // AR(1) step in current regime.
            double inn_std = (st.regime == 0)
                ? normal_innovation_std_
                : congested_innovation_std_;
            double lm = log_mean_for(st.regime, inn_std);

            std::normal_distribution<double> noise(0.0, inn_std);
            double new_log = lm + rho_ * (st.log_state - lm) + noise(rng_);

            st.log_state = new_log;
            return std::exp(new_log);
        }

        default:
            throw std::runtime_error("Unknown mode");
    }

    return 0.0;
}

void RegimeLatencyModel::update_regime(int load)
{
    double p_nc = regime_switch_prob(load);
    double p_cn = 0.05;

    std::bernoulli_distribution bern_nc(p_nc);
    std::bernoulli_distribution bern_cn(p_cn);

    if (regime_ == Regime::NORMAL) {
        if (bern_nc(rng_)) regime_ = Regime::CONGESTED;
    } else {
        if (bern_cn(rng_)) regime_ = Regime::NORMAL;
    }
}

double RegimeLatencyModel::regime_switch_prob(int load)
{
    return std::min(0.3, load / congestion_threshold_ * 0.1);
}