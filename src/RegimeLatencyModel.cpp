#include "RegimeLatencyModel.hpp"
#include <random>
#include <fstream>
#include <cmath>

static std::mt19937 rng(42);


RegimeLatencyModel::RegimeLatencyModel(Mode mode, const LatencyParams& p)
    : mode_(mode),
      regime_(Regime::NORMAL),

      normal_mean_(p.normal_mean),
      congested_mean_(p.congested_mean),

      normal_std_(p.normal_std),
      congested_std_(p.congested_std),

      congestion_threshold_(p.congestion_threshold),

      noise_std_(p.noise_std),
      rho_(p.rho),

      base_delay_(p.base_delay),
      bandwidth_(p.bandwidth),
      packet_size_(p.packet_size)
{}


double RegimeLatencyModel::sample(int sender, int receiver, double t, int load, int queue_size)
{
    switch (mode_) {

        case Mode::NO_DELAY:
            return 0.0;

        case Mode::IID: {
            std::normal_distribution<double> dist(normal_mean_, normal_std_);
            return std::max(0.0, dist(rng));
        }
        case Mode::IID_EXPONENTIAL: {
            double lambda = 1.0 / normal_mean_;
            std::exponential_distribution<double> dist(lambda);
            return dist(rng);
        }
        case Mode::REGIME: {
            update_regime(load);

            std::normal_distribution<double> dist(
                regime_ == Regime::NORMAL ? normal_mean_ : congested_mean_,
                regime_ == Regime::NORMAL ? normal_std_ : congested_std_
            );

            return std::max(0.0, dist(rng));
        }

        case Mode::CORRELATED: {
            auto key = std::make_pair(sender, receiver);

            double prev = 0.0;
            auto it = prev_latency_.find(key);
            if(it != prev_latency_.end()){
                prev = it->second;
            }

            std::normal_distribution<double> noise(0.0, noise_std_);

            double mean = base_delay_ + (queue_size * packet_size_) / bandwidth_;

            double latency = rho_ * prev
                        + (1 - rho_) * mean
                        + noise(rng);

            latency = std::max(0.0, latency);

            prev_latency_[key] = latency;

            return latency;
        }
        default:
            throw std::runtime_error("Unknown mode");
            break;
    }

    return 0.0;
}

void RegimeLatencyModel::update_regime(int load)
{
    double p_nc = regime_switch_prob(load);   // normal to congested
    double p_cn = 0.05;                       // congested to normal 

    std::bernoulli_distribution bern_nc(p_nc);
    std::bernoulli_distribution bern_cn(p_cn);

    if (regime_ == Regime::NORMAL) {
        if (bern_nc(rng)) {
            regime_ = Regime::CONGESTED;
        }
    } else {
        if (bern_cn(rng)) {
            regime_ = Regime::NORMAL;
        }
    }
}

double RegimeLatencyModel::regime_switch_prob(int load)
{
    return std::min(0.3, load / congestion_threshold_ * 0.1);
}