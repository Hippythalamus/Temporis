#include <RegimeLatencyModel.hpp>
#include <random>
#include <cmath>

static std::mt19937 rng(42);


RegimeLatencyModel::RegimeLatencyModel(Mode mode)
    : mode_(mode),
      regime_(Regime::NORMAL),
      normal_mean_(2.0),
      congested_mean_(30.0),
      normal_std_(2.0),
      congested_std_(20.0),
      congestion_threshold_(100)
{}

double RegimeLatencyModel::sample(int sender, int receiver, double t, int load)
{
    switch (mode_) {

        case Mode::NO_DELAY:
            return 0.0;

        case Mode::IID: {
            std::normal_distribution<double> dist(normal_mean_, normal_std_);
            return std::max(0.0, dist(rng));
        }

        case Mode::REGIME: {
            update_regime(load);

            std::normal_distribution<double> dist(
                regime_ == Regime::NORMAL ? normal_mean_ : congested_mean_,
                regime_ == Regime::NORMAL ? normal_std_ : congested_std_
            );

            return std::max(0.0, dist(rng));
        }
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