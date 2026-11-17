import re, os, json

VIDS = {
 '1fcfZ_Ne8ok': [
  (0,'01_intro'),(117,'02_ml_with_python'),(1409,'03_python_intro'),(4044,'04_numpy'),(5878,'05_pandas'),
  (9616,'06_matplotlib'),(11293,'07_best_libs'),(13623,'08_what_is_ml'),(14618,'09_types_of_ml'),
  (15072,'10_math_for_ml'),(21233,'11_select_modeling'),(21962,'12_linear_regression'),
  (22408,'13_least_squares'),(23486,'14_logistic_regression'),(26315,'15_decision_tree'),
  (29049,'16_random_forest'),(30564,'17_knn'),(32507,'18_naive_bayes'),(33809,'19_svm'),
  (34399,'20_kmeans'),(35799,'21_hierarchical'),(36180,'22_apriori'),(37230,'23_interview_qs'),
 ],
 'hDKCxebp88A': [
  (0,'L0_intro'),(135,'L1_linear_regression'),(8250,'L2_logistic_regression'),(17606,'L3_trees_random_forests'),
  (26729,'L4_approach_ml_projects'),(36373,'L5_gbm_xgboost'),(44457,'L6_unsupervised'),(52398,'L7_project_scratch'),
  (63680,'L8_flask_deployment'),
 ],
}

def load(vid):
    lines = open(f'{vid}_transcript.txt', encoding='utf-8').read().split('\n')
    i = lines.index('TRANSCRIPT:')
    out = []
    for ln in lines[i+1:]:
        m = re.match(r'\[(\d+):(\d+)\] (.*)$', ln)
        if m:
            out.append((int(m.group(1))*60 + int(m.group(2)), m.group(3)))
    return out

os.makedirs('parts', exist_ok=True)
for vid, marks in VIDS.items():
    segs = load(vid)
    end = segs[-1][0] if segs else 0
    for k, (t0, name) in enumerate(marks):
        t1 = marks[k+1][0] if k+1 < len(marks) else end + 1
        chunk = [x for (t, x) in segs if t0 <= t < t1]
        path = f'parts/{vid}__{name}.txt'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# {vid} {name}  [{t0//60}m .. {t1//60}m]  lines={len(chunk)}\n")
            # pack ~8 captions per line so grep gives readable windows
            for j in range(0, len(chunk), 8):
                f.write(' '.join(chunk[j:j+8]) + '\n')
        print(f"{os.path.getsize(path):>9,}  {path}")
