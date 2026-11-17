# Overnight report
generated 2026-11-17 23:00

Accuracy = vote of the 4 predictors on a held-out 30% (grouped split), mean of the last 30 rounds, best variant per dataset. 'majority' = always guessing the biggest class.

## Per modality

| modality | datasets | mean accuracy | mean majority | at 03:20 start |
|---|---|---|---|---|
| text | 14 | 91.1% | 35.4% | 90.4% (14 sets) |
| image | 13 | 92.0% | 9.6% | 91.1% (11 sets) |
| audio | 8 | 68.8% | 9.3% | 72.3% (6 sets) |
| video | 2 | 85.0% | 9.5% | 64.2% (1 sets) |
| graph | 9 | 81.2% | 58.3% | 81.1% (9 sets) |
| **all** | **46** | **85.3%** | | 85.3% (41 sets) |

## Datasets new since 03:20 (and not in the first table)

- audio/birdcleftop20: 6.5%  (enc2 v4, majority 6.9%)
- audio/speech_commands_v0.02: 72.6%  (enc v4, majority 3.8%)
- image/food101: 83.4%  (enc2 v4, majority 1.1%)
- image/imagenet_100: 93.5%  (enc2 v4, majority 1.1%)
- video/ucf101_subset: 98.9%  (enc2 v4, majority 10.9%)

## Changes on datasets that existed at 03:20 (points of accuracy)

- audio/ravdess: +19.0  (enc v2 -> enc2 v4)
- audio/cremad_parquet: +15.1  (enc v2 -> enc2 v4)
- text/amazon_polarity: +8.3  (enc v3 -> enc2 v4)
- video/hmdb51: +6.9  (enc v3 -> enc2 v4)
- image/cifar100: +4.9  (enc v2 -> enc2 v4)
- image/cifar10: +4.0  (enc v3 -> enc2 v4)
- image/dtd: +3.7  (enc v3 -> enc2 v4)
- image/oxford_iiit_pet: +2.6  (enc v2 -> enc2 v4)
- audio/gtzan: +2.1  (enc v3 -> enc2 v4)
- image/beans: +1.6  (enc v2 -> enc2 v4)
- audio/esc50: +1.4  (enc v3 -> enc2 v4)
- graph/imdb_binary: +1.0  (enc2 v3 -> enc2 v4)
- graph/aids: +0.7  (enc2 v3 -> enc2 v4)
- text/ag_news: +0.6  (enc v3 -> enc2 v4)
- text/enron_spam: +0.4  (enc v3 -> enc2 v4)
- text/bbc_news: +0.4  (enc v3 -> enc2 v4)
- image/cats_vs_dogs: +0.4  (enc v2 -> enc2 v4)
- graph/deezer_ego_nets: +0.4  (enc v3 -> enc2 v4)
- image/resisc45: +0.3  (enc v2 -> enc2 v4)
- image/kmnist: +0.3  (enc v3 -> enc2 v4)
- text/rotten_tomatoes: -0.5  (enc2 v3 -> enc2 v4)
- image/tiny_imagenet: -0.9  (enc v2 -> enc v4)
- graph/ogbg_molhiv: -1.6  (enc v2 -> enc2 v4)

## Weakest datasets now

- graph/deezer_ego_nets: 54.9% (majority 56.8%)
- graph/ogbg_molhiv: 95.5% (majority 96.5%)
- audio/birdcleftop20: 6.5% (majority 6.9%)
- text/sms_spam: 99.2% (majority 86.6%)
- graph/twitch_egos: 68.8% (majority 53.8%)
- graph/proteins: 76.3% (majority 59.6%)
- graph/aids: 99.6% (majority 80.0%)
- graph/mutag: 86.5% (majority 66.5%)

## Encoded feature sets on disk

- enc: 44   enc2 (stronger encoders): 44
- encode failures recorded: {'text/sst2': 1, 'graph/ogbg_ppa': 2, 'video/ucf101': 2}

## Scheduler: last 12 log lines

```
19:51:48 [sched] segment complete auto_gpu_005 after 2.07 h
19:51:51 [sched] START auto_cpu_004 (cpu, est 0.52 GB) pid 28716 tasks=['hand/graph/imdb_binary', 'hand/graph/aids', 'hand/graph/ogbg_molhiv']
21:50:13 [sched] segment complete auto_gpu_007 after 2.07 h
21:50:15 [sched] START auto_cpu_016 (cpu, est 0.62 GB) pid 32152 tasks=['enc/graph/deezer_ego_nets']
21:51:03 [sched] segment complete auto_cpu_013 after 2.04 h
21:51:05 [sched] START auto_cpu_017 (cpu, est 0.51 GB) pid 15880 tasks=['enc/graph/csl']
21:53:33 [sched] segment complete auto_cpu_065 after 2.06 h
21:53:34 [sched] START auto_cpu_021 (cpu, est 0.60 GB) pid 28516 tasks=['enc/image/dtd']
21:54:23 [sched] segment complete auto_cpu_004 after 2.04 h
21:54:24 [sched] START auto_cpu_066 (cpu, est 0.91 GB) pid 32560 tasks=['enc2/audio/cremad_parquet']
21:58:32 [sched] segment complete auto_cpu_014 after 2.13 h
21:58:33 [sched] START auto_cpu_061 (cpu, est 0.58 GB) pid 28712 tasks=['enc2/audio/ravdess']
```

## Findings from the algorithm work

- PROBE_gbdt.md / PROBE_v4.md / PROBE_v4b.md: boosted trees beat the 4-predictor vote on all 6 graph sets; v4 (tree joins only when it beats every predictor on the calibration slice) gave twitch +3.1, imdb_binary +3.5, aids +0.8, deezer +0.75, and was identical to v3 on text/emotion and audio/ravdess.
- GATE_PUBLIC.md: manager trust gate on 3937 public agent runs (SWE-agent trajectories): AUROC ~0.52 = no predictive power from pre-run information; no transfer to your own ledger (0.48). The gate is NOT ready to control a manager.

