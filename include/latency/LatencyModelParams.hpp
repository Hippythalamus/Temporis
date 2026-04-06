#pragma once

struct LatencyParams {
    public:
        double normal_mean;
        double congested_mean;

        double normal_std;
        double congested_std;

        double congestion_threshold;

        double noise_std;
        double rho;

        double base_delay;
        double bandwidth;
        double packet_size;
};