#pragma once
#include <map>
#include "LatencyModel.hpp"
#include "LatencyModelParams.hpp"

class RegimeLatencyModel : public LatencyModel {
public:
    enum class Regime { NORMAL, CONGESTED };
    enum class Mode {
        NO_DELAY,
        IID,
        IID_EXPONENTIAL,
        REGIME, 
        CORRELATED
    };

    RegimeLatencyModel(Mode mode_, const LatencyParams& latency) ;

    double sample(int sender, int receiver, double t, int network_load, int queue_size) override;

private:
    Regime regime_;
    Mode mode_;

    double normal_mean_;
    double congested_mean_;

    double normal_std_;
    double congested_std_;

    double congestion_threshold_;

    double noise_std_;
    std::map<std::pair<int,int>, double> prev_latency_;
    double rho_;
    double base_delay_;
    double bandwidth_ ;
    double packet_size_;

    double regime_switch_prob(int network_load);
    void update_regime(int network_load);
};