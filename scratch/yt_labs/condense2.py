import re, os

KEEP = re.compile(r"""(?xi)
 (?:\d+\.\d+) | (\d+\s?(percent|%)) | (r2|r_squared|mean_squared_error|accuracy|precision|recall|f1|auc|roc|mae|rmse)
 | (\bmodel\b|\.fit|\.predict|\.score|\.transform|get_params|coef_|intercept_|feature_importances)
 | (max_depth|min_samples|n_estimators|learning_rate|eta|early_stopping|C\s*=|gamma|kernel|n_neighbors|metric=)
 | (train_test_split|test_size|random_state|shuffle|StandardScaler|OneHotEncoder|get_dummies|LabelEncoder|column_stack)
 | (GridSearchCV|cross_val|KFold|StratifiedKFold|pipeline|Pipeline)
 | (LinearRegression|LogisticRegression|DecisionTree|RandomForest|GradientBoosting|XGB|xgboost|KMeans|DBSCAN|PCA|TSNE|tsne|fastai)
 | (flask|pickle|joblib|render_template|request\.json|app\.route|Procfile|requirements|localhost|heroku|pythonanywhere)
 | (dataset|csv|columns?|shape|rows?|target|feature|label)
 | (overfit|underfit|regulari|generaliz|linear model|non-?linear|assumption|outlier|missing|nan|null)
 | (for example|for instance|let's|we can see|the value of|it turns out|so we get|we end up|which means)
""", re.X)

os.makedirs('cond2', exist_ok=True)
vid = 'hDKCxebp88A'
raw = open(f'{vid}_transcript.txt', encoding='utf-8').read().split('\n')
i = raw.index('TRANSCRIPT:')
segs = []
for ln in raw[i+1:]:
    m = re.match(r'\[(\d+):(\d+)\] (.*)$', ln)
    if m:
        segs.append((int(m.group(1))*60+int(m.group(2)), m.group(3)))

files = sorted(f for f in os.listdir('parts') if f.startswith(vid))
starts = [int(re.search(r'\[(\d+)m', open(f'parts/{g}', encoding='utf-8').readline()).group(1))*60 for g in files]
for idx, f in enumerate(files):
    t0 = starts[idx]
    t1 = starts[idx+1] if idx+1 < len(files) else 10**9
    chunk = [x for t, x in segs if t0 <= t < t1]
    kept = [x for x in chunk if KEEP.search(x)]
    buf, size = [], 0
    CAP = 13000
    for j in range(0, len(kept), 5):
        line = ' '.join(kept[j:j+5])
        if size + len(line) > CAP:
            break
        buf.append(line); size += len(line) + 1
    path = f'cond2/{f}'
    open(path, 'w', encoding='utf-8').write(f'# {f} kept {len(kept)} lines, showing ~{len(buf)} packed rows\n' + '\n'.join(buf))
    print(f'{os.path.getsize(path):>7,}  cond2/{f}')
