# NI comparison: feature kind and algorithm

Mean of the last 30 rounds per run, against ground-truth labels (held-out 30% window). hand = old hand-built features, enc = frozen pretrained encoder (graphs: Weisfeiler-Lehman fingerprint). v1 = original algorithm, v2 = LDA Logic + class weights + wider MLP, v3 = v2 + calibration slice (per-predictor temperature, log-loss stack weights, class-prior shift on imbalanced tasks) + tuned Verifier + multi-scale Exploratory + seed-ensembled Pattern. v4 = v3 + a boosted-tree learner in the Exploratory slot that joins only when it beats all four predictors on the calibration slice. enc2 = stronger frozen encoders (bge-base text, dinov2-base image, dinov2+VideoMAE+X-CLIP video, AST+Whisper+CLAP audio, rich spectral/WL graph features).

| dataset | variant | rounds | vote acc | uniform acc | balanced acc | AUROC | Logic | best single | majority | inner AUC | vote-conf AUC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| audio/cremad_parquet | enc v2 | 26 (1 run) | 0.607 | 0.599 | 0.609 | - | 0.588 | 0.599 | 0.171 | 0.699 | 0.693 |
| audio/esc50 | hand v1 | 42 (2 runs) | 0.560 | 0.532 | - | - | 0.393 | 0.563 | 0.020 | 0.757 | 0.751 |
| audio/esc50 | enc v1 | 30 (1 run) | 0.956 | 0.950 | - | - | 0.931 | 0.956 | 0.020 | 0.900 | 0.886 |
| audio/esc50 | enc v2 | 7 (1 run) | 0.959 | 0.958 | 0.957 | - | 0.954 | 0.961 | 0.020 | 0.884 | 0.880 |
| audio/esc50 | enc v3 | 23 (1 run) | 0.961 | 0.960 | 0.961 | - | 0.955 | 0.962 | 0.020 | 0.916 | 0.917 |
| audio/gtzan | hand v1 | 30 (1 run) | 0.692 | 0.660 | - | - | 0.464 | 0.686 | 0.100 | - | - |
| audio/gtzan | enc v1 | 33 (2 runs) | 0.863 | 0.864 | - | - | 0.834 | 0.863 | 0.100 | - | - |
| audio/gtzan | enc v2 | 7 (1 run) | 0.872 | 0.872 | 0.871 | - | 0.867 | 0.873 | 0.100 | - | - |
| audio/gtzan | enc v3 | 23 (1 run) | 0.860 | 0.862 | 0.862 | - | 0.858 | 0.862 | 0.100 | - | - |
| audio/music_genres_small | enc v2 | 30 (1 run) | 0.565 | 0.566 | 0.565 | - | 0.556 | 0.563 | 0.100 | - | - |
| audio/ravdess | enc v2 | 30 (1 run) | 0.686 | 0.682 | 0.682 | - | 0.644 | 0.685 | 0.133 | - | - |
| audio/urbansound8k | legacy-hand v1 | 60 (2 runs) | 0.660 | 0.617 | - | - | 0.419 | 0.659 | 0.115 | 0.816 | 0.821 |
| graph/aids | hand v1 | 30 (1 run) | 0.991 | 0.991 | - | - | 0.526 | 0.992 | 0.800 | nan | nan |
| graph/aids | hand v3 | 30 (1 run) | 0.993 | 0.994 | 0.984 | 0.997 | 0.984 | 0.993 | 0.800 | nan | nan |
| graph/aids | enc v2 | 30 (1 run) | 0.984 | 0.981 | 0.962 | 0.992 | 0.984 | 0.984 | 0.800 | nan | nan |
| graph/aids | enc2 v3 | 15 (1 run) | 0.989 | 0.988 | 0.975 | 0.998 | 0.991 | 0.991 | 0.800 | nan | nan |
| graph/csl | enc v3 | 30 (1 run) | 1.000 | 1.000 | 1.000 | - | 1.000 | 1.000 | 0.100 | - | - |
| graph/csl | enc2 v3 | 20 (1 run) | 1.000 | 1.000 | 1.000 | - | 1.000 | 1.000 | 0.100 | - | - |
| graph/deezer_ego_nets | enc v3 | 30 (1 run) | 0.545 | 0.535 | 0.503 | 0.510 | 0.521 | 0.548 | 0.568 | 0.532 | 0.516 |
| graph/imdb_binary | hand v1 | 42 (2 runs) | 0.710 | 0.710 | - | - | 0.709 | 0.723 | 0.500 | - | - |
| graph/imdb_binary | hand v3 | 30 (1 run) | 0.703 | 0.697 | 0.703 | 0.778 | 0.707 | 0.712 | 0.500 | - | - |
| graph/imdb_binary | enc v2 | 30 (1 run) | 0.684 | 0.684 | 0.684 | 0.765 | 0.686 | 0.689 | 0.500 | - | - |
| graph/imdb_binary | enc2 v3 | 18 (1 run) | 0.704 | 0.706 | 0.704 | 0.785 | 0.695 | 0.707 | 0.500 | - | - |
| graph/mutag | legacy-hand v1 | 30 (1 run) | 0.865 | 0.858 | - | - | 0.818 | 0.885 | 0.665 | - | - |
| graph/ogbg_molhiv | hand v1 | 42 (2 runs) | 0.967 | 0.967 | - | - | 0.526 | 0.968 | 0.965 | 0.784 | 0.780 |
| graph/ogbg_molhiv | hand v3 | 30 (1 run) | 0.927 | 0.966 | 0.695 | 0.776 | 0.963 | 0.968 | 0.965 | 0.875 | 0.798 |
| graph/ogbg_molhiv | enc v2 | 30 (1 run) | 0.971 | 0.971 | 0.691 | 0.804 | 0.963 | 0.968 | 0.965 | 0.778 | 0.750 |
| graph/proteins | legacy-hand v1 | 30 (1 run) | 0.763 | 0.770 | - | - | 0.735 | 0.764 | 0.596 | - | - |
| graph/reddit_threads | enc v3 | 30 (1 run) | 0.774 | 0.772 | 0.772 | 0.837 | 0.772 | 0.772 | 0.512 | 0.698 | 0.695 |
| graph/twitch_egos | enc v3 | 30 (1 run) | 0.690 | 0.686 | 0.684 | 0.718 | 0.688 | 0.688 | 0.538 | 0.576 | 0.576 |
| image/beans | enc v2 | 30 (1 run) | 0.942 | 0.940 | 0.942 | - | 0.937 | 0.942 | 0.337 | - | - |
| image/cats_vs_dogs | enc v2 | 19 (1 run) | 0.993 | 0.993 | 0.993 | 1.000 | 0.993 | 0.993 | 0.502 | 0.983 | 0.981 |
| image/cifar10 | legacy-hand v1 | 60 (2 runs) | 0.683 | 0.658 | - | - | 0.414 | 0.680 | 0.100 | 0.834 | 0.808 |
| image/cifar10 | hand v1 | 42 (2 runs) | 0.683 | 0.658 | - | - | 0.414 | 0.680 | 0.100 | 0.826 | 0.801 |
| image/cifar10 | enc v1 | 30 (1 run) | 0.908 | 0.901 | - | - | 0.827 | 0.907 | 0.100 | 0.927 | 0.911 |
| image/cifar10 | enc v2 | 7 (1 run) | 0.911 | 0.907 | 0.912 | - | 0.882 | 0.911 | 0.100 | 0.932 | 0.917 |
| image/cifar10 | enc v3 | 23 (1 run) | 0.905 | 0.900 | 0.906 | - | 0.881 | 0.905 | 0.100 | 0.928 | 0.908 |
| image/cifar100 | hand v1 | 30 (1 run) | 0.380 | 0.371 | - | - | 0.182 | 0.367 | 0.010 | 0.829 | 0.791 |
| image/cifar100 | enc v1 | 34 (2 runs) | 0.841 | 0.838 | - | - | 0.745 | 0.839 | 0.010 | 0.913 | 0.889 |
| image/cifar100 | enc v2 | 30 (1 run) | 0.848 | 0.845 | 0.848 | - | 0.790 | 0.843 | 0.010 | 0.907 | 0.888 |
| image/dtd | enc v3 | 30 (1 run) | 0.750 | 0.750 | 0.751 | - | 0.708 | 0.748 | 0.021 | 0.884 | 0.867 |
| image/emnist_letters | enc v3 | 30 (1 run) | 0.936 | 0.913 | 0.936 | - | 0.887 | 0.936 | 0.038 | 0.925 | 0.921 |
| image/gtsrb | enc v3 | 30 (1 run) | 0.988 | 0.976 | 0.991 | - | 0.892 | 0.978 | 0.059 | 0.991 | 0.985 |
| image/kmnist | enc v3 | 30 (1 run) | 0.971 | 0.950 | 0.971 | - | 0.908 | 0.971 | 0.100 | 0.962 | 0.954 |
| image/oxford_iiit_pet | enc v2 | 25 (1 run) | 0.921 | 0.920 | 0.922 | - | 0.905 | 0.917 | 0.027 | 0.897 | 0.893 |
| image/resisc45 | enc v2 | 22 (1 run) | 0.941 | 0.936 | 0.940 | - | 0.832 | 0.939 | 0.025 | 0.969 | 0.949 |
| image/tiny_imagenet | hand v1 | 30 (1 run) | 0.208 | 0.186 | - | - | 0.098 | 0.201 | 0.005 | 0.776 | 0.762 |
| image/tiny_imagenet | enc v1 | 3 (1 run) | 0.817 | 0.816 | - | - | 0.747 | 0.815 | 0.005 | 0.917 | 0.888 |
| image/tiny_imagenet | enc v2 | 30 (1 run) | 0.821 | 0.824 | 0.821 | - | 0.769 | 0.818 | 0.005 | 0.917 | 0.901 |
| text/20_newsgroups | hand v1 | 43 (2 runs) | 0.592 | 0.585 | - | - | 0.446 | 0.537 | 0.053 | 0.860 | 0.835 |
| text/20_newsgroups | enc v1 | 30 (1 run) | 0.766 | 0.766 | - | - | 0.664 | 0.762 | 0.053 | 0.903 | 0.890 |
| text/20_newsgroups | enc v2 | 7 (1 run) | 0.766 | 0.763 | 0.756 | - | 0.688 | 0.761 | 0.053 | 0.899 | 0.886 |
| text/20_newsgroups | enc v3 | 23 (1 run) | 0.768 | 0.748 | 0.758 | - | 0.685 | 0.765 | 0.053 | 0.896 | 0.885 |
| text/20_newsgroups | enc2 v3 | 30 (1 run) | 0.796 | 0.777 | 0.786 | - | 0.725 | 0.795 | 0.053 | 0.911 | 0.901 |
| text/ag_news | legacy-hand v1 | 60 (2 runs) | 0.891 | 0.886 | - | - | 0.773 | 0.887 | 0.250 | 0.881 | 0.823 |
| text/ag_news | hand v1 | 44 (2 runs) | 0.894 | 0.887 | - | - | 0.773 | 0.887 | 0.250 | 0.863 | 0.824 |
| text/ag_news | enc v1 | 30 (1 run) | 0.929 | 0.924 | - | - | 0.868 | 0.920 | 0.250 | 0.879 | 0.868 |
| text/ag_news | enc v2 | 8 (1 run) | 0.929 | 0.922 | 0.929 | - | 0.894 | 0.921 | 0.250 | 0.880 | 0.871 |
| text/ag_news | enc v3 | 22 (1 run) | 0.927 | 0.918 | 0.927 | - | 0.894 | 0.922 | 0.250 | 0.884 | 0.876 |
| text/amazon_polarity | enc v3 | 30 (1 run) | 0.877 | 0.871 | 0.877 | 0.946 | 0.862 | 0.876 | 0.502 | 0.830 | 0.819 |
| text/banking77 | hand v1 | 43 (2 runs) | 0.810 | 0.665 | - | - | 0.480 | 0.828 | 0.017 | 0.913 | 0.898 |
| text/banking77 | enc v1 | 30 (1 run) | 0.932 | 0.925 | - | - | 0.870 | 0.926 | 0.017 | 0.928 | 0.922 |
| text/banking77 | enc v2 | 8 (1 run) | 0.931 | 0.926 | 0.933 | - | 0.887 | 0.927 | 0.017 | 0.930 | 0.924 |
| text/banking77 | enc v3 | 22 (1 run) | 0.932 | 0.925 | 0.933 | - | 0.889 | 0.930 | 0.017 | 0.928 | 0.923 |
| text/banking77 | enc2 v3 | 30 (1 run) | 0.942 | 0.938 | 0.943 | - | 0.910 | 0.939 | 0.017 | 0.932 | 0.932 |
| text/bbc_news | enc v3 | 22 (1 run) | 0.975 | 0.975 | 0.974 | - | 0.967 | 0.971 | 0.230 | nan | nan |
| text/dbpedia_14 | hand v1 | 30 (1 run) | 0.944 | 0.954 | - | - | 0.853 | 0.937 | 0.073 | 0.959 | 0.935 |
| text/dbpedia_14 | enc v1 | 34 (2 runs) | 0.978 | 0.975 | - | - | 0.940 | 0.978 | 0.073 | 0.948 | 0.931 |
| text/dbpedia_14 | enc v2 | 8 (1 run) | 0.979 | 0.976 | 0.979 | - | 0.966 | 0.979 | 0.073 | 0.945 | 0.933 |
| text/dbpedia_14 | enc v3 | 22 (1 run) | 0.978 | 0.974 | 0.978 | - | 0.966 | 0.978 | 0.073 | 0.950 | 0.941 |
| text/dbpedia_14 | enc2 v3 | 30 (1 run) | 0.987 | 0.985 | 0.987 | - | 0.980 | 0.987 | 0.073 | 0.956 | 0.952 |
| text/emotion | enc v3 | 30 (1 run) | 0.730 | 0.738 | 0.703 | - | 0.688 | 0.745 | 0.338 | 0.838 | 0.764 |
| text/emotion | enc2 v3 | 30 (1 run) | 0.782 | 0.780 | 0.761 | - | 0.746 | 0.793 | 0.338 | 0.845 | 0.769 |
| text/enron_spam | enc v3 | 30 (1 run) | 0.989 | 0.986 | 0.989 | 0.999 | 0.973 | 0.987 | 0.509 | 0.987 | 0.975 |
| text/imdb | enc v3 | 30 (1 run) | 0.811 | 0.814 | 0.811 | 0.895 | 0.785 | 0.794 | 0.500 | 0.806 | 0.775 |
| text/imdb | enc2 v3 | 30 (1 run) | 0.923 | 0.921 | 0.923 | 0.976 | 0.914 | 0.922 | 0.500 | 0.896 | 0.876 |
| text/rotten_tomatoes | enc v3 | 30 (1 run) | 0.765 | 0.774 | 0.765 | 0.843 | 0.762 | 0.762 | 0.500 | 0.746 | 0.710 |
| text/rotten_tomatoes | enc2 v3 | 30 (1 run) | 0.866 | 0.866 | 0.866 | 0.939 | 0.861 | 0.862 | 0.500 | 0.814 | 0.812 |
| text/sms_spam | enc v2 | 30 (1 run) | 0.991 | 0.991 | 0.976 | 0.994 | 0.986 | 0.990 | 0.866 | nan | nan |
| text/sms_spam | enc2 v3 | 30 (1 run) | 0.992 | 0.992 | 0.978 | 0.996 | 0.989 | 0.992 | 0.866 | 0.932 | 0.889 |
| text/sst2 | enc v2 | 30 (1 run) | 0.810 | 0.812 | 0.810 | 0.893 | 0.808 | 0.808 | 0.516 | 0.779 | 0.766 |
| text/sst2 | enc2 v3 | 30 (1 run) | 0.910 | 0.909 | 0.910 | 0.969 | 0.905 | 0.907 | 0.516 | 0.875 | 0.869 |
| text/yahoo_answers_topics | enc2 v3 | 30 (1 run) | 0.746 | 0.743 | 0.747 | - | 0.724 | 0.738 | 0.101 | 0.819 | 0.814 |
| text/yelp_polarity | enc v2 | 28 (1 run) | 0.874 | 0.869 | 0.874 | 0.946 | 0.863 | 0.874 | 0.501 | 0.843 | 0.833 |
| text/yelp_polarity | enc2 v3 | 30 (1 run) | 0.950 | 0.949 | 0.950 | 0.989 | 0.945 | 0.949 | 0.501 | 0.916 | 0.910 |
| video/hmdb51 | legacy-hand v1 | 30 (1 run) | 0.321 | 0.313 | - | - | 0.210 | 0.315 | 0.264 | 0.645 | 0.647 |
| video/hmdb51 | hand v1 | 30 (1 run) | 0.163 | 0.161 | - | - | 0.097 | 0.161 | 0.081 | 0.685 | 0.662 |
| video/hmdb51 | enc v1 | 30 (1 run) | 0.616 | 0.578 | - | - | 0.478 | 0.613 | 0.081 | 0.800 | 0.783 |
| video/hmdb51 | enc v2 | 9 (1 run) | 0.641 | 0.623 | 0.633 | - | 0.617 | 0.626 | 0.081 | 0.823 | 0.813 |
| video/hmdb51 | enc v3 | 21 (1 run) | 0.642 | 0.631 | 0.649 | - | 0.622 | 0.633 | 0.081 | 0.811 | 0.808 |

## Gains (vote accuracy, points)

| dataset | hand -> enc | enc v1 -> v2 | enc v2 -> v3 | enc v3 -> v4 | enc -> enc2 (best algo) | note |
|---|---|---|---|---|---|---|
| audio/cremad_parquet | - | - | - | - | - |  |
| audio/esc50 | +39.8 | +0.3 | +0.2 | - | - |  |
| audio/gtzan | +18.0 | +0.9 | -1.2 | - | - |  |
| audio/music_genres_small | - | - | - | - | - |  |
| audio/ravdess | - | - | - | - | - |  |
| audio/urbansound8k | - | - | - | - | - |  |
| graph/aids | -0.7 | - | - | - | +0.5 |  |
| graph/csl | - | - | - | - | +0.0 |  |
| graph/deezer_ego_nets | - | - | - | - | - |  |
| graph/imdb_binary | -2.6 | - | - | - | +2.0 |  |
| graph/mutag | - | - | - | - | - |  |
| graph/ogbg_molhiv | +0.4 | - | - | - | - | hand features at majority-class level (accuracy alone hides this; see balanced acc / AUROC) |
| graph/proteins | - | - | - | - | - |  |
| graph/reddit_threads | - | - | - | - | - |  |
| graph/twitch_egos | - | - | - | - | - |  |
| image/beans | - | - | - | - | - |  |
| image/cats_vs_dogs | - | - | - | - | - |  |
| image/cifar10 | +22.8 | +0.3 | -0.6 | - | - |  |
| image/cifar100 | +46.7 | +0.7 | - | - | - |  |
| image/dtd | - | - | - | - | - |  |
| image/emnist_letters | - | - | - | - | - |  |
| image/gtsrb | - | - | - | - | - |  |
| image/kmnist | - | - | - | - | - |  |
| image/oxford_iiit_pet | - | - | - | - | - |  |
| image/resisc45 | - | - | - | - | - |  |
| image/tiny_imagenet | +61.3 | +0.4 | - | - | - |  |
| text/20_newsgroups | +17.4 | +0.0 | +0.2 | - | +2.9 |  |
| text/ag_news | +3.5 | +0.0 | -0.2 | - | - |  |
| text/amazon_polarity | - | - | - | - | - |  |
| text/banking77 | +12.1 | -0.1 | +0.1 | - | +1.0 |  |
| text/bbc_news | - | - | - | - | - |  |
| text/dbpedia_14 | +3.5 | +0.1 | -0.1 | - | +0.9 |  |
| text/emotion | - | - | - | - | +5.2 |  |
| text/enron_spam | - | - | - | - | - |  |
| text/imdb | - | - | - | - | +11.3 |  |
| text/rotten_tomatoes | - | - | - | - | +10.0 |  |
| text/sms_spam | - | - | - | - | +0.1 |  |
| text/sst2 | - | - | - | - | +9.9 |  |
| text/yahoo_answers_topics | - | - | - | - | - |  |
| text/yelp_polarity | - | - | - | - | +7.7 |  |
| video/hmdb51 | +47.8 | +2.5 | +0.2 | - | - |  |

Read honestly: runs differ in how many rounds they got (several were killed by GPU faults), so compare the tables, not single numbers; 'enc v1 -> v2' is only filled where both algorithms trained the same dataset.
