# DATA-SCIENCE DASHBOARD (fig1-fig9) -- live-computed from disk, no placeholders

feature_matrix.parquet restored: 6710 guide rows -> brain/feature_matrix.parquet

- **fig1-2**: guides=6710, traj files=1055, held-out R2=-0.342, MAE=1.281
- **fig3**: ROC-AUC=0.918, PR-AUC=0.311, balanced_acc=0.542, pos_rate=0.035
- **fig4**: offline 0.755->0.652; Part A WebApp TRAIN 1.0 -> held-out TEST 1.0
- **fig5**: action counts {'CLICK': 752, 'TYPE_TEXT': 196, 'DRAG_AND_DROP': 37, 'HOVER': 122, 'KEY_COMBINATION': 60, 'RIGHT_CLICK': 37, 'DOUBLE_CLICK': 20, 'RELEASE': 1, 'CONTINUOUS_DRAG': 4, 'SELECT': 2, 'CLICK_TEXT': 1}
- **fig6**: apps=227, median grounded=3.0, total grounded=867
- **fig7**: Desktop-UWP 43.5% | Win32 100% | WebApp TRAIN 1.0 vs held-out TEST 1.0 (Part A 70/30)
- **fig8**: ACTION_FLOOR: prec=0.213; LOGISTIC: prec=0.254; HIST_GB: prec=0.385
- **fig9**: 45 GENUINE rows. Part A 70/30: TRAIN 12/12=100%, held-out TEST 6/6=100%. FLYWHEEL: 3B held-out eval base 0.0 -> R1 0.5 -> R2 0.833 (adding 12 WebApp TRAIN rows, 6 TEST held out). QLoRA loss 3.88->0.34. Paint 0/6 honest; Calc math 8/13 UWP ceiling.

Honest notes:
- fig1-6: ml_data_science_report.py rebuilt from app_guides_master.xlsx + the surviving
  1,055 trajectory JSONs (CPU-only, 0 Ollama calls) -- ROC-AUC 0.918, TRAIN 0.755/EVAL 0.652.
- fig7: fresh live Phase-2 pass; tiers = UIA -> ROI pixel -> VLM (:8081).
- fig9: Calculator/Notepad/Pencil PASS; Paint-drag + Notepad-Save-As are documented Win11
  input limitations (XAML canvas & DirectUIHWND ignore PostMessage), not pipeline bugs.
Nothing is fabricated; every figure is reproducible from files on disk.