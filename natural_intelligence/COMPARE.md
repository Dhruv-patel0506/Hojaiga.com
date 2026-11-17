# NI comparison: feature kind and algorithm

Mean of the last 30 rounds per run, against ground-truth labels (held-out 30% window). hand = old hand-built features, enc = frozen pretrained encoder (graphs: Weisfeiler-Lehman fingerprint). v1 = original algorithm, v2 = LDA Logic + class weights + wider MLP, v3 = v2 + calibration slice (per-predictor temperature, log-loss stack weights, class-prior shift on imbalanced tasks) + tuned Verifier + multi-scale Exploratory + seed-ensembled Pattern. v4 = v3 + a boosted-tree learner in the Exploratory slot that joins only when it beats all four predictors on the calibration slice. enc2 = stronger frozen encoders (bge-base text, dinov2-base image, dinov2+VideoMAE+X-CLIP video, AST+Whisper+CLAP audio, rich spectral/WL graph features).

| dataset | variant | rounds | vote acc | uniform acc | balanced acc | AUROC | Logic | best single | majority | inner AUC | vote-conf AUC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| audio/birdcleftop20 | enc v4 | 30 (1 run) | 0.064 | 0.065 | 0.050 | - | 0.063 | 0.069 | 0.069 | 0.501 | 0.499 |
| audio/birdcleftop20 | enc2 v4 | 30 (1 run) | 0.065 | 0.065 | 0.050 | - | 0.064 | 0.068 | 0.069 | 0.498 | 0.496 |
| audio/cremad_parquet | enc v4 | 30 (1 run) | 0.601 | 0.594 | 0.602 | - | 0.588 | 0.599 | 0.171 | 0.714 | 0.704 |
| audio/cremad_parquet | enc2 v4 | 30 (1 run) | 0.758 | 0.739 | 0.760 | - | 0.741 | 0.752 | 0.171 | 0.797 | 0.797 |
| audio/esc50 | hand v1 | 42 (2 runs) | 0.560 | 0.532 | - | - | 0.393 | 0.563 | 0.020 | 0.757 | 0.751 |
| audio/esc50 | enc v1 | 30 (1 run) | 0.956 | 0.950 | - | - | 0.931 | 0.956 | 0.020 | 0.900 | 0.886 |
| audio/esc50 | enc v4 | 30 (1 run) | 0.954 | 0.954 | 0.955 | - | 0.950 | 0.956 | 0.020 | 0.917 | 0.924 |
| audio/esc50 | enc2 v4 | 30 (1 run) | 0.975 | 0.972 | 0.976 | - | 0.973 | 0.975 | 0.020 | nan | nan |
| audio/gtzan | hand v1 | 30 (1 run) | 0.692 | 0.660 | - | - | 0.464 | 0.686 | 0.100 | - | - |
| audio/gtzan | enc v1 | 33 (2 runs) | 0.863 | 0.864 | - | - | 0.834 | 0.863 | 0.100 | - | - |
| audio/gtzan | enc v4 | 30 (1 run) | 0.860 | 0.860 | 0.862 | - | 0.859 | 0.865 | 0.100 | - | - |
| audio/gtzan | enc2 v4 | 30 (1 run) | 0.881 | 0.877 | 0.883 | - | 0.881 | 0.883 | 0.100 | - | - |
| audio/music_genres_small | enc v4 | 30 (1 run) | 0.547 | 0.552 | 0.548 | - | 0.542 | 0.556 | 0.100 | - | - |
| audio/music_genres_small | enc2 v4 | 30 (1 run) | 0.566 | 0.566 | 0.567 | - | 0.555 | 0.575 | 0.100 | - | - |
| audio/ravdess | enc v4 | 30 (1 run) | 0.692 | 0.677 | 0.688 | - | 0.650 | 0.692 | 0.133 | - | - |
| audio/ravdess | enc2 v4 | 30 (1 run) | 0.876 | 0.868 | 0.875 | - | 0.853 | 0.874 | 0.133 | - | - |
| audio/speech_commands_v0.02 | enc v4 | 30 (1 run) | 0.726 | 0.714 | 0.720 | - | 0.679 | 0.727 | 0.038 | 0.887 | 0.864 |
| audio/urbansound8k | legacy-hand v1 | 60 (2 runs) | 0.660 | 0.617 | - | - | 0.419 | 0.659 | 0.115 | 0.816 | 0.821 |
| graph/aids | hand v1 | 30 (1 run) | 0.991 | 0.991 | - | - | 0.526 | 0.992 | 0.800 | nan | nan |
| graph/aids | hand v4 | 30 (1 run) | 0.997 | 0.996 | 0.992 | 0.997 | 0.983 | 0.997 | 0.800 | nan | nan |
| graph/aids | enc v4 | 30 (1 run) | 0.992 | 0.986 | 0.981 | 0.996 | 0.985 | 0.996 | 0.800 | nan | nan |
| graph/aids | enc2 v4 | 30 (1 run) | 0.996 | 0.991 | 0.991 | 0.997 | 0.990 | 0.997 | 0.800 | nan | nan |
| graph/csl | enc v4 | 30 (1 run) | 1.000 | 1.000 | 1.000 | - | 1.000 | 1.000 | 0.100 | - | - |
| graph/csl | enc2 v4 | 30 (1 run) | 1.000 | 1.000 | 1.000 | - | 1.000 | 1.000 | 0.100 | - | - |
| graph/deezer_ego_nets | enc v4 | 30 (1 run) | 0.546 | 0.534 | 0.501 | 0.507 | 0.519 | 0.550 | 0.568 | 0.543 | 0.525 |
| graph/deezer_ego_nets | enc2 v4 | 30 (1 run) | 0.549 | 0.538 | 0.503 | 0.512 | 0.519 | 0.552 | 0.568 | 0.536 | 0.516 |
| graph/imdb_binary | hand v1 | 42 (2 runs) | 0.710 | 0.710 | - | - | 0.709 | 0.723 | 0.500 | - | - |
| graph/imdb_binary | hand v4 | 30 (1 run) | 0.717 | 0.714 | 0.717 | 0.790 | 0.718 | 0.729 | 0.500 | - | - |
| graph/imdb_binary | enc v4 | 30 (1 run) | 0.712 | 0.705 | 0.712 | 0.797 | 0.691 | 0.715 | 0.500 | - | - |
| graph/imdb_binary | enc2 v4 | 30 (1 run) | 0.714 | 0.706 | 0.715 | 0.800 | 0.693 | 0.715 | 0.500 | - | - |
| graph/mutag | legacy-hand v1 | 30 (1 run) | 0.865 | 0.858 | - | - | 0.818 | 0.885 | 0.665 | - | - |
| graph/ogbg_molhiv | hand v1 | 42 (2 runs) | 0.967 | 0.967 | - | - | 0.526 | 0.968 | 0.965 | 0.784 | 0.780 |
| graph/ogbg_molhiv | hand v4 | 30 (1 run) | 0.934 | 0.967 | 0.701 | 0.781 | 0.963 | 0.968 | 0.965 | 0.879 | 0.810 |
| graph/ogbg_molhiv | enc v4 | 30 (1 run) | 0.952 | 0.971 | 0.745 | 0.822 | 0.963 | 0.970 | 0.965 | 0.869 | 0.794 |
| graph/ogbg_molhiv | enc2 v4 | 30 (1 run) | 0.955 | 0.971 | 0.743 | 0.823 | 0.964 | 0.970 | 0.965 | 0.865 | 0.815 |
| graph/proteins | legacy-hand v1 | 30 (1 run) | 0.763 | 0.770 | - | - | 0.735 | 0.764 | 0.596 | - | - |
| graph/reddit_threads | enc v3 | 1 (1 run) | 0.776 | 0.773 | 0.774 | 0.838 | 0.773 | 0.773 | 0.512 | 0.696 | 0.692 |
| graph/reddit_threads | enc v4 | 29 (1 run) | 0.773 | 0.771 | 0.772 | 0.836 | 0.772 | 0.772 | 0.512 | 0.698 | 0.694 |
| graph/reddit_threads | enc2 v4 | 19 (1 run) | 0.774 | 0.772 | 0.773 | 0.836 | 0.776 | 0.776 | 0.512 | 0.703 | 0.694 |
| graph/twitch_egos | enc v4 | 30 (1 run) | 0.689 | 0.686 | 0.683 | 0.717 | 0.688 | 0.688 | 0.538 | 0.578 | 0.578 |
| graph/twitch_egos | enc2 v4 | 30 (1 run) | 0.688 | 0.685 | 0.682 | 0.716 | 0.681 | 0.683 | 0.538 | 0.580 | 0.580 |
| image/beans | enc v4 | 30 (1 run) | 0.944 | 0.943 | 0.944 | - | 0.937 | 0.946 | 0.337 | - | - |
| image/beans | enc2 v4 | 30 (1 run) | 0.958 | 0.955 | 0.958 | - | 0.958 | 0.960 | 0.337 | - | - |
| image/cats_vs_dogs | enc v4 | 30 (1 run) | 0.994 | 0.993 | 0.994 | 1.000 | 0.993 | 0.993 | 0.502 | 0.977 | 0.984 |
| image/cats_vs_dogs | enc2 v4 | 21 (1 run) | 0.997 | 0.997 | 0.997 | 1.000 | 0.997 | 0.997 | 0.502 | 0.937 | 0.953 |
| image/cifar10 | legacy-hand v1 | 60 (2 runs) | 0.683 | 0.658 | - | - | 0.414 | 0.680 | 0.100 | 0.834 | 0.808 |
| image/cifar10 | hand v1 | 42 (2 runs) | 0.683 | 0.658 | - | - | 0.414 | 0.680 | 0.100 | 0.826 | 0.801 |
| image/cifar10 | enc v1 | 30 (1 run) | 0.908 | 0.901 | - | - | 0.827 | 0.907 | 0.100 | 0.927 | 0.911 |
| image/cifar10 | enc v4 | 30 (1 run) | 0.907 | 0.902 | 0.907 | - | 0.881 | 0.906 | 0.100 | 0.928 | 0.906 |
| image/cifar10 | enc2 v4 | 29 (1 run) | 0.945 | 0.942 | 0.945 | - | 0.932 | 0.943 | 0.100 | 0.948 | 0.938 |
| image/cifar100 | hand v1 | 30 (1 run) | 0.380 | 0.371 | - | - | 0.182 | 0.367 | 0.010 | 0.829 | 0.791 |
| image/cifar100 | enc v1 | 34 (2 runs) | 0.841 | 0.838 | - | - | 0.745 | 0.839 | 0.010 | 0.913 | 0.889 |
| image/cifar100 | enc v2 | 20 (1 run) | 0.848 | 0.845 | 0.848 | - | 0.790 | 0.843 | 0.010 | 0.906 | 0.889 |
| image/cifar100 | enc v4 | 10 (1 run) | 0.837 | 0.830 | 0.837 | - | 0.789 | 0.836 | 0.010 | 0.912 | 0.889 |
| image/cifar100 | enc2 v4 | 30 (1 run) | 0.897 | 0.895 | 0.897 | - | 0.865 | 0.894 | 0.010 | 0.928 | 0.920 |
| image/dtd | enc v4 | 30 (1 run) | 0.751 | 0.750 | 0.752 | - | 0.709 | 0.750 | 0.021 | 0.879 | 0.866 |
| image/dtd | enc2 v4 | 30 (1 run) | 0.787 | 0.780 | 0.788 | - | 0.749 | 0.783 | 0.021 | 0.870 | 0.860 |
| image/emnist_letters | enc v3 | 1 (1 run) | 0.937 | 0.913 | 0.937 | - | 0.888 | 0.937 | 0.038 | 0.927 | 0.924 |
| image/emnist_letters | enc v4 | 29 (1 run) | 0.936 | 0.913 | 0.936 | - | 0.887 | 0.936 | 0.038 | 0.925 | 0.920 |
| image/food101 | enc v4 | 30 (1 run) | 0.756 | 0.745 | 0.756 | - | 0.716 | 0.756 | 0.011 | 0.898 | 0.883 |
| image/food101 | enc2 v4 | 30 (1 run) | 0.834 | 0.818 | 0.834 | - | 0.792 | 0.832 | 0.011 | 0.908 | 0.897 |
| image/gtsrb | enc v4 | 30 (1 run) | 0.988 | 0.976 | 0.991 | - | 0.892 | 0.978 | 0.059 | 0.991 | 0.984 |
| image/imagenet_100 | enc v4 | 30 (1 run) | 0.894 | 0.893 | 0.892 | - | 0.862 | 0.894 | 0.011 | 0.935 | 0.921 |
| image/imagenet_100 | enc2 v4 | 14 (1 run) | 0.935 | 0.932 | 0.933 | - | 0.915 | 0.933 | 0.011 | 0.933 | 0.928 |
| image/kmnist | enc v4 | 30 (1 run) | 0.971 | 0.949 | 0.971 | - | 0.907 | 0.971 | 0.100 | 0.959 | 0.953 |
| image/kmnist | enc2 v4 | 30 (1 run) | 0.974 | 0.955 | 0.974 | - | 0.927 | 0.974 | 0.100 | 0.956 | 0.952 |
| image/oxford_iiit_pet | enc v4 | 30 (1 run) | 0.921 | 0.920 | 0.921 | - | 0.909 | 0.920 | 0.027 | 0.923 | 0.911 |
| image/oxford_iiit_pet | enc2 v4 | 30 (1 run) | 0.947 | 0.943 | 0.947 | - | 0.936 | 0.947 | 0.027 | 0.930 | 0.920 |
| image/resisc45 | enc v4 | 30 (1 run) | 0.934 | 0.926 | 0.934 | - | 0.830 | 0.934 | 0.025 | 0.971 | 0.945 |
| image/resisc45 | enc2 v4 | 14 (1 run) | 0.944 | 0.934 | 0.943 | - | 0.863 | 0.943 | 0.025 | 0.969 | 0.958 |
| image/tiny_imagenet | hand v1 | 30 (1 run) | 0.208 | 0.186 | - | - | 0.098 | 0.201 | 0.005 | 0.776 | 0.762 |
| image/tiny_imagenet | enc v1 | 3 (1 run) | 0.817 | 0.816 | - | - | 0.747 | 0.815 | 0.005 | 0.917 | 0.888 |
| image/tiny_imagenet | enc v4 | 30 (1 run) | 0.812 | 0.807 | 0.812 | - | 0.767 | 0.810 | 0.005 | 0.918 | 0.898 |
| text/20_newsgroups | hand v1 | 43 (2 runs) | 0.592 | 0.585 | - | - | 0.446 | 0.537 | 0.053 | 0.860 | 0.835 |
| text/20_newsgroups | enc v1 | 30 (1 run) | 0.766 | 0.766 | - | - | 0.664 | 0.762 | 0.053 | 0.903 | 0.890 |
| text/20_newsgroups | enc v4 | 30 (1 run) | 0.768 | 0.749 | 0.758 | - | 0.686 | 0.765 | 0.053 | 0.895 | 0.879 |
| text/20_newsgroups | enc2 v4 | 30 (1 run) | 0.798 | 0.779 | 0.788 | - | 0.727 | 0.797 | 0.053 | 0.912 | 0.899 |
| text/ag_news | legacy-hand v1 | 60 (2 runs) | 0.891 | 0.886 | - | - | 0.773 | 0.887 | 0.250 | 0.881 | 0.823 |
| text/ag_news | hand v1 | 44 (2 runs) | 0.894 | 0.887 | - | - | 0.773 | 0.887 | 0.250 | 0.863 | 0.824 |
| text/ag_news | enc v1 | 30 (1 run) | 0.929 | 0.924 | - | - | 0.868 | 0.920 | 0.250 | 0.879 | 0.868 |
| text/ag_news | enc v3 | 4 (1 run) | 0.926 | 0.918 | 0.926 | - | 0.894 | 0.922 | 0.250 | 0.884 | 0.876 |
| text/ag_news | enc v4 | 26 (1 run) | 0.927 | 0.918 | 0.927 | - | 0.894 | 0.923 | 0.250 | 0.883 | 0.875 |
| text/ag_news | enc2 v4 | 30 (1 run) | 0.933 | 0.927 | 0.933 | - | 0.910 | 0.929 | 0.250 | 0.893 | 0.881 |
| text/amazon_polarity | enc v4 | 30 (1 run) | 0.877 | 0.871 | 0.877 | 0.946 | 0.862 | 0.877 | 0.502 | 0.834 | 0.822 |
| text/amazon_polarity | enc2 v4 | 21 (1 run) | 0.960 | 0.960 | 0.960 | 0.991 | 0.958 | 0.959 | 0.502 | 0.912 | 0.907 |
| text/banking77 | hand v1 | 43 (2 runs) | 0.810 | 0.665 | - | - | 0.480 | 0.828 | 0.017 | 0.913 | 0.898 |
| text/banking77 | enc v1 | 30 (1 run) | 0.932 | 0.925 | - | - | 0.870 | 0.926 | 0.017 | 0.928 | 0.922 |
| text/banking77 | enc v3 | 2 (1 run) | 0.935 | 0.926 | 0.933 | - | 0.893 | 0.933 | 0.017 | 0.935 | 0.925 |
| text/banking77 | enc v4 | 28 (1 run) | 0.931 | 0.925 | 0.933 | - | 0.889 | 0.930 | 0.017 | 0.931 | 0.925 |
| text/banking77 | enc2 v4 | 30 (1 run) | 0.941 | 0.939 | 0.943 | - | 0.910 | 0.939 | 0.017 | 0.931 | 0.928 |
| text/bbc_news | enc v4 | 30 (1 run) | 0.970 | 0.972 | 0.969 | - | 0.964 | 0.969 | 0.230 | 0.893 | 0.926 |
| text/bbc_news | enc2 v4 | 30 (1 run) | 0.979 | 0.979 | 0.979 | - | 0.972 | 0.979 | 0.230 | nan | nan |
| text/dbpedia_14 | hand v1 | 30 (1 run) | 0.944 | 0.954 | - | - | 0.853 | 0.937 | 0.073 | 0.959 | 0.935 |
| text/dbpedia_14 | enc v1 | 34 (2 runs) | 0.978 | 0.975 | - | - | 0.940 | 0.978 | 0.073 | 0.948 | 0.931 |
| text/dbpedia_14 | enc v3 | 2 (1 run) | 0.978 | 0.973 | 0.978 | - | 0.965 | 0.978 | 0.073 | 0.944 | 0.932 |
| text/dbpedia_14 | enc v4 | 28 (1 run) | 0.978 | 0.974 | 0.978 | - | 0.966 | 0.978 | 0.073 | 0.948 | 0.938 |
| text/dbpedia_14 | enc2 v4 | 30 (1 run) | 0.987 | 0.985 | 0.987 | - | 0.979 | 0.987 | 0.073 | 0.955 | 0.950 |
| text/emotion | enc v4 | 30 (1 run) | 0.734 | 0.739 | 0.701 | - | 0.688 | 0.746 | 0.338 | 0.841 | 0.773 |
| text/emotion | enc2 v4 | 30 (1 run) | 0.781 | 0.780 | 0.760 | - | 0.744 | 0.792 | 0.338 | 0.850 | 0.770 |
| text/enron_spam | enc v4 | 30 (1 run) | 0.990 | 0.985 | 0.989 | 0.999 | 0.972 | 0.987 | 0.509 | 0.985 | 0.981 |
| text/enron_spam | enc2 v4 | 30 (1 run) | 0.993 | 0.991 | 0.993 | 1.000 | 0.983 | 0.992 | 0.509 | 0.991 | 0.973 |
| text/imdb | enc v4 | 30 (1 run) | 0.808 | 0.813 | 0.808 | 0.892 | 0.784 | 0.794 | 0.500 | 0.809 | 0.775 |
| text/imdb | enc2 v4 | 30 (1 run) | 0.923 | 0.921 | 0.923 | 0.976 | 0.914 | 0.922 | 0.500 | 0.895 | 0.876 |
| text/rotten_tomatoes | enc v4 | 30 (1 run) | 0.764 | 0.772 | 0.764 | 0.843 | 0.761 | 0.761 | 0.500 | 0.744 | 0.711 |
| text/rotten_tomatoes | enc2 v4 | 30 (1 run) | 0.861 | 0.862 | 0.861 | 0.937 | 0.858 | 0.859 | 0.500 | 0.823 | 0.817 |
| text/sms_spam | enc v4 | 30 (1 run) | 0.991 | 0.991 | 0.975 | 0.995 | 0.986 | 0.991 | 0.866 | 0.690 | 0.883 |
| text/sms_spam | enc2 v4 | 30 (1 run) | 0.992 | 0.992 | 0.984 | 0.997 | 0.990 | 0.992 | 0.866 | nan | nan |
| text/sst2 | enc v4 | 30 (1 run) | 0.812 | 0.815 | 0.812 | 0.894 | 0.810 | 0.810 | 0.516 | 0.786 | 0.766 |
| text/sst2 | enc2 v4 | 30 (1 run) | 0.911 | 0.909 | 0.910 | 0.969 | 0.905 | 0.907 | 0.516 | 0.867 | 0.864 |
| text/yahoo_answers_topics | enc v4 | 30 (1 run) | 0.741 | 0.735 | 0.742 | - | 0.710 | 0.733 | 0.101 | 0.811 | 0.807 |
| text/yahoo_answers_topics | enc2 v3 | 2 (1 run) | 0.746 | 0.743 | 0.747 | - | 0.724 | 0.737 | 0.101 | 0.811 | 0.808 |
| text/yahoo_answers_topics | enc2 v4 | 28 (1 run) | 0.747 | 0.743 | 0.747 | - | 0.724 | 0.738 | 0.101 | 0.820 | 0.816 |
| text/yelp_polarity | enc v4 | 30 (1 run) | 0.874 | 0.868 | 0.874 | 0.945 | 0.863 | 0.873 | 0.501 | 0.838 | 0.825 |
| text/yelp_polarity | enc2 v4 | 30 (1 run) | 0.950 | 0.949 | 0.950 | 0.988 | 0.945 | 0.949 | 0.501 | 0.916 | 0.902 |
| video/hmdb51 | legacy-hand v1 | 30 (1 run) | 0.321 | 0.313 | - | - | 0.210 | 0.315 | 0.264 | 0.645 | 0.647 |
| video/hmdb51 | hand v1 | 30 (1 run) | 0.163 | 0.161 | - | - | 0.097 | 0.161 | 0.081 | 0.685 | 0.662 |
| video/hmdb51 | enc v1 | 30 (1 run) | 0.616 | 0.578 | - | - | 0.478 | 0.613 | 0.081 | 0.800 | 0.783 |
| video/hmdb51 | enc v3 | 5 (1 run) | 0.636 | 0.624 | 0.645 | - | 0.618 | 0.629 | 0.081 | 0.825 | 0.813 |
| video/hmdb51 | enc v4 | 25 (1 run) | 0.637 | 0.625 | 0.646 | - | 0.613 | 0.630 | 0.081 | 0.805 | 0.786 |
| video/hmdb51 | enc2 v4 | 30 (1 run) | 0.711 | 0.688 | 0.722 | - | 0.606 | 0.711 | 0.081 | 0.817 | 0.813 |
| video/ucf101_subset | enc v4 | 30 (1 run) | 0.956 | 0.943 | 0.958 | - | 0.957 | 0.958 | 0.109 | - | - |
| video/ucf101_subset | enc2 v4 | 30 (1 run) | 0.989 | 0.983 | 0.989 | - | 0.973 | 0.989 | 0.109 | - | - |

## Gains (vote accuracy, points)

| dataset | hand -> enc | enc v1 -> v2 | enc v2 -> v3 | enc v3 -> v4 | enc -> enc2 (best algo) | note |
|---|---|---|---|---|---|---|
| audio/birdcleftop20 | - | - | - | - | +0.1 |  |
| audio/cremad_parquet | - | - | - | - | +15.7 |  |
| audio/esc50 | +39.5 | - | - | - | +2.1 |  |
| audio/gtzan | +17.1 | - | - | - | +2.1 |  |
| audio/music_genres_small | - | - | - | - | +1.9 |  |
| audio/ravdess | - | - | - | - | +18.4 |  |
| audio/speech_commands_v0.02 | - | - | - | - | - |  |
| audio/urbansound8k | - | - | - | - | - |  |
| graph/aids | - | - | - | - | +0.4 |  |
| graph/csl | - | - | - | - | +0.0 |  |
| graph/deezer_ego_nets | - | - | - | - | +0.3 |  |
| graph/imdb_binary | - | - | - | - | +0.1 |  |
| graph/mutag | - | - | - | - | - |  |
| graph/ogbg_molhiv | - | - | - | - | +0.3 | hand features at majority-class level (accuracy alone hides this; see balanced acc / AUROC) |
| graph/proteins | - | - | - | - | - |  |
| graph/reddit_threads | - | - | - | -0.2 | +0.1 |  |
| graph/twitch_egos | - | - | - | - | -0.1 |  |
| image/beans | - | - | - | - | +1.4 |  |
| image/cats_vs_dogs | - | - | - | - | +0.3 |  |
| image/cifar10 | +22.5 | - | - | - | +3.8 |  |
| image/cifar100 | +46.8 | +0.7 | - | - | +6.0 |  |
| image/dtd | - | - | - | - | +3.5 |  |
| image/emnist_letters | - | - | - | -0.1 | - |  |
| image/food101 | - | - | - | - | +7.7 |  |
| image/gtsrb | - | - | - | - | - |  |
| image/imagenet_100 | - | - | - | - | +4.1 |  |
| image/kmnist | - | - | - | - | +0.2 |  |
| image/oxford_iiit_pet | - | - | - | - | +2.6 |  |
| image/resisc45 | - | - | - | - | +1.0 |  |
| image/tiny_imagenet | +60.9 | - | - | - | - |  |
| text/20_newsgroups | +17.4 | - | - | - | +3.1 |  |
| text/ag_news | +3.5 | - | - | +0.0 | +0.6 |  |
| text/amazon_polarity | - | - | - | - | +8.3 |  |
| text/banking77 | +12.2 | - | - | -0.3 | +1.0 |  |
| text/bbc_news | - | - | - | - | +0.9 |  |
| text/dbpedia_14 | +3.4 | - | - | +0.0 | +0.8 |  |
| text/emotion | - | - | - | - | +4.7 |  |
| text/enron_spam | - | - | - | - | +0.4 |  |
| text/imdb | - | - | - | - | +11.4 |  |
| text/rotten_tomatoes | - | - | - | - | +9.7 |  |
| text/sms_spam | - | - | - | - | +0.2 |  |
| text/sst2 | - | - | - | - | +9.9 |  |
| text/yahoo_answers_topics | - | - | - | - | +0.6 |  |
| text/yelp_polarity | - | - | - | - | +7.6 |  |
| video/hmdb51 | +45.3 | - | - | +0.1 | +7.4 |  |
| video/ucf101_subset | - | - | - | - | +3.3 |  |

Read honestly: runs differ in how many rounds they got (several were killed by GPU faults), so compare the tables, not single numbers; 'enc v1 -> v2' is only filled where both algorithms trained the same dataset.
