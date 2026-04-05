#pragma once
#include "LatencyModel.hpp"

class RegimeLatencyModel : public LatencyModel {
public:
    enum class Regime { NORMAL, CONGESTED };
    enum class Mode {
        NO_DELAY,
        IID,
        REGIME
    };

    RegimeLatencyModel(Mode mode_);

    double sample(int sender, int receiver, double t, int network_load) override;

private:
    Regime regime_;
    Mode mode_;

    double normal_mean_;
    double congested_mean_;

    double normal_std_;
    double congested_std_;

    double congestion_threshold_;

    double regime_switch_prob(int network_load);
    void update_regime(int network_load);
};