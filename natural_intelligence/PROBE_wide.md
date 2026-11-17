## probe 2026-11-07 19:00  algos=v2,v3 rounds=3 cap=12000 device=cpu

| task | algo | n_tr | vote acc | balanced acc | AUROC | NLL | Logic | Pattern | Verifier | Explor. | sec/round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/ogbg_molhiv | v2 | 8413 | 0.9699 | 0.6405 | 0.7848 | 0.1444 | 0.963 | 0.964 | 0.964 | 0.968 | 46.4 |
| enc/graph/ogbg_molhiv | v3 | 8413 | 0.9049 | 0.7169 | 0.7912 | 0.3482 | 0.963 | 0.966 | 0.969 | 0.969 | 76.8 |
|  | v3 diag | | {"n_fit": 7357, "n_cal": 1003, "D": 550, "imbalance": 29.53, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [0.7, 0.5, 1.4, 0.5], "stack": [1.018, 0.928, 0.976, 1.078], "prior_shift": 0.75} |
| enc/text/sst2 | v2 | 6751 | 0.8157 | 0.8155 | 0.8946 | 0.4160 | 0.811 | 0.802 | 0.727 | 0.765 | 54.9 |
| enc/text/sst2 | v3 | 6751 | 0.8171 | 0.8168 | 0.8967 | 0.4180 | 0.810 | 0.799 | 0.765 | 0.798 | 16.1 |
|  | v3 diag | | {"n_fit": 5885, "n_cal": 802, "D": 384, "imbalance": 1.06, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 2.0, 0.7, 0.7], "stack": [1.082, 0.976, 0.968, 0.974], "prior_shift": 0.0} |
| enc/text/imdb | v2 | 8337 | 0.7902 | 0.7901 | 0.8697 | 0.4583 | 0.771 | 0.765 | 0.721 | 0.728 | 14.8 |
| enc/text/imdb | v3 | 8337 | 0.7806 | 0.7803 | 0.8670 | 0.4676 | 0.768 | 0.764 | 0.741 | 0.747 | 18.0 |
|  | v3 diag | | {"n_fit": 7372, "n_cal": 1005, "D": 384, "imbalance": 1.03, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 2.0, 0.7, 0.7], "stack": [1.039, 1.105, 1.022, 0.834], "prior_shift": 0.0} |
| enc/text/emotion | v2 | 8460 | 0.7342 | 0.6318 | nan | 0.8215 | 0.672 | 0.724 | 0.658 | 0.603 | 15.9 |
| enc/text/emotion | v3 | 8460 | 0.6901 | 0.6841 | nan | 0.8996 | 0.673 | 0.717 | 0.682 | 0.639 | 18.7 |
|  | v3 diag | | {"n_fit": 7345, "n_cal": 1001, "D": 384, "imbalance": 9.54, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [0.7, 1.0, 0.7, 0.5], "stack": [0.665, 1.793, 0.991, 0.551], "prior_shift": 1.0} |
| enc/text/banking77 | v2 | 8432 | 0.9212 | 0.9213 | nan | 0.3739 | 0.884 | 0.921 | 0.916 | 0.897 | 20.5 |
| enc/text/banking77 | v3 | 8432 | 0.9222 | 0.9223 | nan | 0.2809 | 0.882 | 0.919 | 0.913 | 0.896 | 25.8 |
|  | v3 diag | | {"n_fit": 7427, "n_cal": 1012, "D": 384, "imbalance": 3.78, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.05, "T": [1.0, 0.7, 1.0, 0.35], "stack": [0.615, 1.676, 1.034, 0.675], "prior_shift": 0.0} |
| enc/audio/esc50 | v2 | 1392 | 0.9646 | 0.9658 | nan | 0.2335 | 0.957 | 0.963 | 0.948 | 0.951 | 13.6 |
| enc/audio/esc50 | v3 | 1392 | 0.9662 | 0.9667 | nan | 0.1256 | 0.959 | 0.966 | 0.947 | 0.960 | 19.1 |
|  | v3 diag | | {"n_fit": 1255, "n_cal": 171, "D": 768, "imbalance": 1.63, "pattern_seeds": 3, "verifier_k": 15, "verifier_tau": 0.05, "T": [1.4, 0.7, 1.0, 0.35], "stack": [0.75, 1.134, 1.239, 0.877], "prior_shift": 0.0} |
| enc/audio/gtzan | v2 | 672 | 0.8648 | 0.8629 | nan | 0.4734 | 0.857 | 0.864 | 0.841 | 0.846 | 10.4 |
| enc/audio/gtzan | v3 | 672 | 0.8568 | 0.8548 | nan | 0.4503 | 0.857 | 0.858 | 0.834 | 0.851 | 15.5 |
|  | v3 diag | | {"n_fit": 600, "n_cal": 81, "D": 768, "imbalance": 1.33, "pattern_seeds": 3, "verifier_k": 15, "verifier_tau": 0.05, "T": [1.4, 0.7, 1.4, 0.7], "stack": [0.575, 1.61, 1.272, 0.543], "prior_shift": 0.0} |
| enc/video/hmdb51 | v2 | 4755 | 0.6192 | 0.6170 | nan | 1.4868 | 0.619 | 0.621 | 0.471 | 0.515 | 23.7 |
| enc/video/hmdb51 | v3 | 4755 | 0.6364 | 0.6403 | nan | 1.3540 | 0.614 | 0.632 | 0.472 | 0.550 | 24.9 |
|  | v3 diag | | {"n_fit": 4026, "n_cal": 548, "D": 1536, "imbalance": 7.95, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.05, "T": [1.0, 0.7, 1.4, 0.5], "stack": [0.774, 2.384, 0.492, 0.35], "prior_shift": 0.5} |
| enc/graph/reddit_threads | v2 | 8393 | 0.7392 | 0.7375 | 0.7995 | 0.5449 | 0.752 | 0.736 | 0.684 | 0.720 | 18.6 |
| enc/graph/reddit_threads | v3 | 8393 | 0.7443 | 0.7428 | 0.8087 | 0.5368 | 0.750 | 0.734 | 0.706 | 0.742 | 21.0 |
|  | v3 diag | | {"n_fit": 7402, "n_cal": 1009, "D": 534, "imbalance": 1.09, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [0.7, 1.4, 1.4, 0.7], "stack": [1.294, 0.952, 0.697, 1.057], "prior_shift": 0.0} |
| enc/graph/aids | v2 | 1363 | 0.9838 | 0.9586 | 0.9897 | 0.0864 | 0.984 | 0.982 | 0.977 | 0.951 | 10.3 |
| enc/graph/aids | v3 | 1363 | 0.9827 | 0.9579 | 0.9878 | 0.0724 | 0.983 | 0.980 | 0.972 | 0.956 | 16.1 |
|  | v3 diag | | {"n_fit": 1226, "n_cal": 167, "D": 608, "imbalance": 3.64, "pattern_seeds": 3, "verifier_k": 15, "verifier_tau": 0.1, "T": [0.7, 0.5, 0.7, 0.35], "stack": [1.163, 1.066, 0.891, 0.879], "prior_shift": 0.0} |
| enc/image/cifar100 | v2 | 8505 | 0.8034 | 0.8044 | nan | 0.8715 | 0.775 | 0.788 | 0.743 | 0.740 | 27.6 |
| enc/image/cifar100 | v3 | 8505 | 0.8002 | 0.8017 | nan | 0.7331 | 0.774 | 0.792 | 0.741 | 0.750 | 30.8 |
|  | v3 diag | | {"n_fit": 7370, "n_cal": 1004, "D": 768, "imbalance": 1.75, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.05, "T": [0.7, 0.7, 1.0, 0.35], "stack": [0.858, 1.844, 0.66, 0.638], "prior_shift": 0.0} |
| enc/image/dtd | v2 | 3923 | 0.7437 | 0.7461 | nan | 0.9590 | 0.693 | 0.738 | 0.706 | 0.689 | 17.8 |
| enc/image/dtd | v3 | 3923 | 0.7429 | 0.7454 | nan | 0.9219 | 0.695 | 0.740 | 0.697 | 0.698 | 24.4 |
|  | v3 diag | | {"n_fit": 3483, "n_cal": 474, "D": 768, "imbalance": 1.38, "pattern_seeds": 3, "verifier_k": 40, "verifier_tau": 0.05, "T": [1.0, 1.0, 1.4, 0.5], "stack": [0.887, 1.772, 0.73, 0.611], "prior_shift": 0.0} |

