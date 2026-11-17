# HANDOFF: ML & Data Science "Live Lab" (single-file HTML study notes)

You are taking over a half-finished project. Read this file first, then `AUTHORING.md` (conventions + per-lesson plans),
then the top comments of `js/00_core.js` and `js/01_engine.js`, then skim `js/lessons/12_linreg.js` (reference lesson).
Everything is plain HTML/CSS/JS with a tiny Python build script. No frameworks, no npm packages in the output.

---------------------------------------------------------------------------------------------------------------------

## 1. The user and the vision

User: Dhruv Patel (cybersecurity CS graduate, learning ML/data science). He turns YouTube videos into **study notes as a
single self-contained HTML file per video**, modelled on his example labs in `reference/` (NumPy labs, determinant,
linear algebra, `cross-product.html`, etc.).

What he asked for, in his words (cleaned up):
* "if I give you a YouTube video, turn it into HTML based on the example I give... not separate, all together in one."
* Two videos -> **two HTML files, one per video**, each with everything the video teaches in that single file:
  1. Edureka "Machine Learning with Python Full Course [2026]" https://www.youtube.com/watch?v=1fcfZ_Ne8ok
  2. freeCodeCamp "Machine Learning with Python and Scikit-Learn" (Aakash N S / Jovian) https://www.youtube.com/watch?v=hDKCxebp88A&t=65s
* Interactive: **show the code, the practical, and the explanation, with visualizations**.
* "Make it more animated like `cross-product.html`" and "make the code more detailed, **not an overview: each section is a
  whole learning section that includes almost everything used in data science from the web, and each topic is visualized.**"
* A **final quiz whose questions and answers constantly change** so nothing can be memorised, and which is **fully logical**
  (every answer computed, distractors from real mistakes, a worked explanation).
* Transcripts could not be fetched (YouTube bot protection), so content follows the chapter lists he screenshotted
  (`reference/chapters_video1_edureka.png`, `reference/chapters_video2_freecodecamp.png`; transcribed in section 6).

The look and feel to match (see `reference/cross-product.html`): left = animated **visual** card and a school-notebook
pane (ruled paper, hand-working with the real numbers); right = a dark **terminal pane** that "types" each code cell and prints
its output; a **step player** (prev/play/next, speed, step list) drives everything; light/dark theme.

---------------------------------------------------------------------------------------------------------------------

## 2. What exists now (in `/home/claude/mllab`, built into `build/ml_datascience_lab.html`, ~608 KB)

Architecture (do not rewrite; extend):
* `shell.html`, `shell.css`: page skeleton + all CSS. `build.py`: concatenates `js/00_core.js`, `js/01_engine.js`,
  `js/lessons/*.js`, `js/9[0-8]_*.js`, `js/99_boot.js` into one HTML. `test.js`: Playwright test harness.
* `js/00_core.js`: helpers (RNG, numpy-compatible stats, `npA`/`dfs`/`sers` printers that mimic NumPy/pandas output exactly,
  SVG primitives `P.*`, `Chart()`, `svg()`, `vtable()`, `lstsq`, `eigSym`, `normCdf`, etc.).
* `js/01_engine.js`: `addLesson`, step `Player`, python highlighter, `Quiz` engine, `Interview` flashcards.
* `js/99_boot.js`: nav, ORDER of lessons, groups (`Python & data`, `ML foundations`, `Supervised learning`,
  `Unsupervised learning`, `Bonus`, `Practice`), final-quiz and interview pages. Lessons missing from ORDER are skipped
  gracefully, so adding a file = adding a lesson.

**Finished and passing `node test.js --sweep` with no console errors (19 lessons, ~7,800 lines):**

| id | file | group | content |
|---|---|---|---|
| py | 01_py.js | Python & data | Python essentials for DS |
| numpy | 02_numpy.js | Python & data | arrays, indexing, broadcasting, axis ops, linalg |
| pandas | 03_pandas.js | Python & data | DataFrame, loc/iloc, groupby, merge, pivot... |
| mpl | 04_mpl.js | Python & data | Matplotlib + Seaborn |
| eda | 05_eda.js | Python & data | describe, IQR/outliers, skew/log, covariance/Pearson/Spearman, cleaning |
| mlintro | 06_mlintro.js | ML foundations | rules vs learning, supervised/unsupervised/RL, X/y, workflow, params vs hyper-params, estimator chooser |
| stats | 07_stats.js | ML foundations | mean/var, z-score/normal, Bayes, binomial, CLT, confidence interval, z-test |
| prep | 09_prep.js | ML foundations | imputer, scalers, encoders, binning, poly features, split, leakage, Pipeline |
| metrics | 10_metrics.js | ML foundations | confusion matrix, PRF1, ROC/AUC, regression metrics, CV, classification_report |
| linreg | 12_linreg.js | Supervised | least squares, gradient descent, sklearn (REFERENCE LESSON) |
| logreg | 13_logreg.js | Supervised | sigmoid, log-loss, Newton/IRLS, boundary, softmax |
| tree, forest | 14_tree_forest.js | Supervised | real CART (+pruning), bootstrap forest, OOB, importances |
| knn | 15_knn.js | Supervised | distance, vote, k choice, scaling, regression |
| nb | 16_nb.js | Supervised | Bayes spam, CountVectorizer, Laplace, Gaussian/Multinomial/Bernoulli |
| svm | 17_svm.js | Supervised | real SMO, margin, C, kernels, RBF/gamma, GridSearchCV |
| kmeans | 18_kmeans.js | Unsupervised | k-means++, Lloyd steps, elbow, silhouette |
| hier | 19_hier.js | Unsupervised | linkage, dendrogram, cophenetic, cut |
| apriori | 20_apriori.js | Unsupervised | support/confidence/lift, level-wise search (just finished; passes) |

Each lesson has 7-10 steps; every step = hand-worked notebook lines + a real Python cell + exact printed output + an animated
SVG. Plus per-lesson "Read first" concept card, cheat-sheet table, pitfalls list, and 2 "quick check" quiz questions.

**Key engineering principle ("exactness")**: the data is generated by a seeded JS RNG and printed *literally* in the Python
cell; the terminal output is computed in JS from the same numbers, and the algorithms (CART, SMO, k-means, linkage, Newton...)
are genuinely implemented in JS, so what the terminal "prints" is what Python would print. Where a library's internal RNG
or tolerance matters, the output ends with a muted comment line saying digits can differ slightly.

---------------------------------------------------------------------------------------------------------------------

## 3. What is NOT built yet (your job)

### 3a. Edureka lab (video 1) - remaining pieces
Write these files exactly as specified in `AUTHORING.md` ("Lesson plans" section has the full contents per lesson):

1. `js/lessons/08_linalg.js`, id `linalg`, group `ML foundations`: vectors, dot/cosine, 2x2 transforms with unit-square morph and
   determinant=area, solving Ax=b/inverse, eigenvectors, derivative/tangent, gradient descent with learning-rate slider
   (converge/oscillate), partial derivatives and gradient on 2-D contours with descent path, chain rule on a one-neuron loss.
2. `js/lessons/11_overfit.js`, id `overfit`, group `ML foundations`: polynomial degree slider (train vs test MSE via lstsq),
   U-shaped test curve, bias-variance bundle of refits, Ridge/Lasso (ridge exact), learning curves, validation curve/GridSearchCV, remedies.
3. `js/lessons/21_boost.js`, id `boost`, group `Bonus`: gradient boosting regression from scratch with stumps, learning rate
   and stage sliders, AdaBoost reweighting, XGBoost/LightGBM usage cheat-sheet, early stopping, overfitting with too many stages.
4. `js/lessons/22_pca.js`, id `pca`, group `Bonus`: centre, covariance, eigen (`eigSym`), projection animation, scree plot
   (4-D synthetic), sklearn PCA calls with the sign rule (largest |loading| positive), PCA before KNN/clustering, when not to use it.
5. `js/90_quiz_bank.js`: `Quiz.label(tag, name)` for every tag (py, numpy, pandas, mpl, eda, mlintro, stats, linalg, prep,
   metrics, overfit, linreg, logreg, tree, forest, knn, nb, svm, kmeans, hier, apriori, boost, pca), **>= 5 generators per tag**
   (linreg already has 2; add 3) and **40-60 `Interview.add(tag, q, a)` cards**.
   Generator contract: `Quiz.add(tag, r => ({text, correct, wrong:[...], why}))` where `r` is a fresh seeded RNG. Fresh random
   numbers every time; `correct` is *computed*; `wrong` has >= 4 distinct options from classic mistakes (n vs n-1, forgot sqrt,
   swapped precision/recall, wrong axis, off-by-one slice...; >= 5 for conceptual questions so the shown distractors rotate);
   `why` shows the worked solution; return `null` when the random draw is degenerate. Mix computational, "what does this code
   print?" (computed), and conceptual questions. See the two examples at the bottom of `12_linreg.js`.
   Test: `node test.js --file=build/ml_datascience_lab.html --quiz`.
6. Final assembly: `python3 build.py --out build/ml_datascience_lab.html && node test.js --sweep --quiz`, then look at screenshots.
   Known minor issues: pandas step 8 label overlap; prep step-2 raw number-line has no tick labels.
7. Optional polish: a "progress" indicator for lessons seen, a print stylesheet, a top-level search over cheat sheets.

### 3b. freeCodeCamp lab (video 2) - NOT started
Second deliverable: `build/ml_fcc_sklearn_lab.html`. Reuse the same engine (copy the project, new `js/lessons/` set, new ORDER/GROUP_ORDER
in 99_boot.js and a different title in shell.html). Same style, same exactness rules, its own quiz bank. Plan (from the chapter list, section 6):

| id | lesson (video chapter) | steps to cover (each a full section, 7-10 steps) |
|---|---|---|
| fcc-intro | Introduction + how the course works | ML vs traditional programming, tools (Jupyter, sklearn, pandas), jovian-style workflow; reuse parts of `mlintro` |
| fcc-linreg | Lesson 1: Linear Regression and Gradient Descent | house/insurance-charges style dataset (age, bmi, smoker...); EDA; one-feature line by hand; loss (MSE/RMSE); OLS vs gradient descent; `LinearRegression`, `SGDRegressor`; multiple features; categorical encoding (smoker, region one-hot); scaling; train/test split; R2/RMSE; predictions function; improve the model |
| fcc-logreg | Lesson 2: Logistic Regression for Classification | Rain-in-Australia style tabular pipeline: missing values, imputer, scaler, one-hot, time-based split, `LogisticRegression(solver='liblinear')`, accuracy, confusion matrix, probabilities, baseline models ("always No", random), predicting on new input, saving the model with joblib |
| fcc-trees | Lesson 3: Decision Trees and Random Forests | tree training/visualisation (`plot_tree`, `export_text`), feature importance, overfitting vs `max_depth`/`max_leaf_nodes`, hyper-parameter tuning curves, random forest, `n_estimators`, `max_features`, `min_samples_split`, class_weight, OOB; reuse the CART/forest code in `14_tree_forest.js` |
| fcc-approach | Lesson 4: How to Approach ML Projects | the end-to-end checklist: frame the problem, get data, EDA, baseline, feature engineering, split/CV, model selection, tuning, error analysis, report; "how to approach a Kaggle-style competition"; data leakage; reproducibility |
| fcc-xgb | Lesson 5: Gradient Boosting Machines with XGBoost | boosting from scratch (residuals, shrinkage), `XGBClassifier/Regressor`, key params (`n_estimators`, `learning_rate`, `max_depth`, `subsample`, `colsample_bytree`, `reg_alpha/lambda`), early stopping, K-fold CV, feature importance, saving; reuse `21_boost.js` |
| fcc-unsup | Lesson 6: Unsupervised Learning using Scikit-Learn | clustering (k-means, DBSCAN, hierarchical), dimensionality reduction (PCA, t-SNE explained), matrix factorisation / recommendation (MovieLens-style: user-item matrix, SVD/ALS idea, cosine similarity) |
| fcc-project | Lesson 7: ML project from scratch (NYC taxi fare) | large-data handling (sampling, dtypes), datetime features, outlier clipping by lat/long bounds, distance features (haversine), baselines, Ridge/RF/XGB comparisons, hyper-param tuning, submission file |
| fcc-deploy | Lesson 8: Deploying a ML project with Flask | saving model + preprocessor with joblib, Flask app skeleton (`@app.route`, `request.get_json`, `jsonify`), HTML form, calling the API with `requests`/curl, folder layout, running locally; deploy (Render/Heroku-style) steps; diagram of request flow animated |

For this file the data is smaller than the real course datasets: generate a seeded synthetic dataset with the same columns and meaning,
state clearly in the notes that it is a stand-in, and keep the code identical to what one would run on the real data.

---------------------------------------------------------------------------------------------------------------------

## 4. How to write a lesson (summary; full rules in AUTHORING.md)

```js
'use strict';
(function () {
  addLesson({
    id: 'xyz', group: 'Supervised learning', title: '...', short: '...', tag: '(...)',
    goal: 'one line', concept: '<div class="two">...</div><div class="callout">...</div>',
    params: [ {id:'seed', type:'seed', value:3, label:'New data'}, {id:'k', type:'range', min:1, max:9, step:1, value:3} ],
    build(p) {                       // rebuilt on every param change
      const data = ...;              // seeded RNG, real algorithm, real numbers
      return [ { title, note:[...], code:`python...`, out:`exact printed text`, viz: t => svg(...) }, ... ];
    },
    cheat: [['df.groupby("a").mean()', 'meaning']], pitfalls: ['...'], quiz: ['xyz'],
  });
})();
```
Rules that matter most: every printed number is computed (never invented); python code lines <= 80 chars; no NaN/undefined in
any string for any slider value; each step's visual differs and teaches that step; notebook lines use `>` (no-wrap math) and `~`
(muted); no emojis; modern APIs (NumPy 2, pandas 2, scikit-learn 1.5+, matplotlib 3.9).

## 5. Build / test / review loop

```
cd /home/claude/mllab            # (or wherever you unzip)
python3 build.py --out build/x/ml.html --files 22_pca.js                       # reference lesson 12 is auto-included
node test.js pca --file=build/x/ml.html --sweep --shots=shots/pca              # needs: npm i playwright && npx playwright install chromium
```
Fix every FAIL (bad tokens, long lines, sweep errors, console errors). Then open the PNGs in `shots/<name>/` and fix overlaps/clipping.
Full build: `python3 build.py` (writes `build/ml_datascience_lab.html`). Work lesson by lesson and test each before the next.
Lesson from the previous session: running many parallel sub-agents hit rate limits; write sequentially.

Past pitfalls worth knowing: long `>` notebook lines clip (keep short); entropy printing -0.0 (write `(p*np.log2(1/p)).sum()`);
fixed outliers can make an SVM `C` slider look inert (compute the outlier from the hard-margin boundary); RBF kernel values can print 0.0
if you choose far points (pick a nearby pair); always include a muted note when output depends on a library RNG.

---------------------------------------------------------------------------------------------------------------------

## 6. Source material: the chapter lists (transcribed from his screenshots)

**Video 1: Edureka, Machine Learning with Python Full Course** (timestamps):
00:00 Introduction | 01:57 Machine Learning with Python | 23:29 Introduction to Python | 1:07:24 NumPy | 1:37:58 Pandas |
2:40:16 Matplotlib | 3:08:13 Best Python libraries for DS & ML | 3:47:03 What is ML? | 4:03:38 Types of ML models |
4:11:12 Mathematics for ML | 5:53:53 How to select the correct predictive modelling technique | 6:06:02 Linear Regression |
6:13:28 Least Squares Regression using Python | 6:31:26 Logistic Regression | 7:18:35 Decision Tree | 8:04:09 Random Forest |
8:29:24 KNN | 9:01:47 Naive Bayes | 9:23:29 SVM | 9:33:19 K-Means | 9:56:39 Hierarchical Clustering | 10:03:00 Apriori |
10:20:30 ML Interview Questions & Answers.

**Video 2: freeCodeCamp, ML with Python and Scikit-Learn (Aakash N S / Jovian):**
00:00 Introduction | 00:25 L1 Linear Regression and Gradient Descent | 2:17:30 L2 Logistic Regression for Classification |
4:53:26 L3 Decision Trees and Random Forests | 7:25:29 L4 How to Approach ML Projects | 10:06:13 L5 Gradient Boosting Machines with XGBoost |
12:20:57 L6 Unsupervised Learning using Scikit-Learn | 13:53:18 L7 ML Project from Scratch (NYC taxi) | 16:45:47 L8 Deploying an ML Project with Flask.

## 7. Deliverables checklist for the next Claude

1. `build/ml_datascience_lab.html`: all 23 lessons + final quiz + interview corner, passing `node test.js --sweep --quiz`.
2. `build/ml_fcc_sklearn_lab.html`: the 9 lessons of section 3b + its own quiz bank + interview cards.
3. Both single-file, open offline (only Google Fonts links are online), work in light and dark, usable on a phone width.
4. A short note to the user: what was built, caveats (no transcripts so content follows chapter lists; stand-in datasets; outputs
   marked library-RNG dependent).
