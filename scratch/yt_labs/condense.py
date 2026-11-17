import re, os

MARK = re.compile(r"""
 (?xi)
 (?:\d)                       # any digit (worked numbers)
 | \b(numpy|pandas|matplotlib|seaborn|scipy|sklearn|scikit|jupyter|anaconda|colab|flask|xgboost|joblib|pickle|statsmodels)\b
 | (?:def |import |\.fit\(|\.predict|\.score|\.transform|\.iloc|\.loc|head\(|describe\(|info\(|value_counts)
 | \b(formula|equation|theorem|derivative|differentiat|gradient|coefficient|intercept|slope|constant|lambda|alpha)\b
 | \b(mean|median|mode|variance|deviation|covariance|correlation|probabilit|likelihood|odds|entropy|gini|impurity|information gain)
 | \b(matrix|vector|dimension|eigen|transpose|dot product|scalar|norm|kernel|hyperplane|margin|support vector)
 | \b(binomial|bernoulli|poisson|normal distribution|gaussian|hypothesis test|chi.?square|bayes|prior|posterior)
 | \b(sigmoid|logistic|hypothesis|least square|residual|sum of squared|overfit|underfit|regulari|bias|variance trade)
 | \b(decision tree|root node|leaf|split|pruning|random forest|bagging|boosting|ensemble|voting|bootstrap)
 | \b(k.?nearest|knn|euclidean|manhattan|centroid|cluster|elbow|silhouette|dendrogram|linkage|anomaly|outlier)
 | \b(apriori|support|confidence|lift|association|frequent itemset|market basket)
 | \b(train|test|validat|split|cross.?validation|grid ?search|hyperparameter|accuracy|precision|recall|f1|auc|roc|confusion|mae|rmse|mse|r2|r squared)
 | \b(one hot|dummy|categorical|encoding|scale|normali|standardi|missing|nan|null|impute)
 | \b(gradient descent|learning rate|epoch|iteration|cost function|loss function|converge|global minimum|local minimum)
 | \b(supervised|unsupervised|semi.?supervised|reinforcement|classification|regression|clustering|recommendation)
 | \b(dataset|data set|columns?|features?|target|label|independent variable|dependent variable|row)
 | \b(for example|for instance|let'?s say|consider|in other words|i'?ll explain|that means|which means|is defined as|we call this)
""", re.X)

os.makedirs('cond', exist_ok=True)
for vid in ['1fcfZ_Ne8ok', 'hDKCxebp88A']:
    raw = [ln for ln in open(f'{vid}_transcript.txt', encoding='utf-8').read().split('\n')]
    i = raw.index('TRANSCRIPT:')
    segs = []
    for ln in raw[i+1:]:
        m = re.match(r'\[(\d+):(\d+)\] (.*)$', ln)
        if m:
            segs.append((int(m.group(1))*60+int(m.group(2)), m.group(3)))
    files = sorted(f for f in os.listdir('parts') if f.startswith(vid))
    for f in files:
        head = open(f'parts/{f}', encoding='utf-8').readline()
        t0 = int(re.search(r'\[(\d+)m', head).group(1)) * 60
        nxt = None
        out = []
        for t, x in segs:
            if t < t0:
                continue
            out.append((t, x))
        # bound by next part start
        starts = sorted(int(re.search(r'\[(\d+)m', open(f'parts/{g}', encoding='utf-8').readline()).group(1)) * 60 for g in files)
        upper = min([s for s in starts if s > t0] or [10**9])
        kept = [(t, x) for t, x in out if t < upper and MARK.search(x)]
        with open(f'cond/{f}', 'w', encoding='utf-8') as fh:
            fh.write(f'# {f}  condensed {len(kept)}/{sum(1 for t,_ in out if t < upper)} lines\n')
            for j in range(0, len(kept), 6):
                fh.write(' '.join(x for _, x in kept[j:j+6]) + '\n')
        print(f'{os.path.getsize(f"cond/{f}"):>8,}  cond/{f}')
