#
# 処理内容：学習モデルを作成
# 作成日：2022/9/12
#
import joblib
import pandas as pd
import numpy as np
from sklearn.svm import SVR
import tomli
import os
# from sklearn import svm
from sklearn.ensemble import GradientBoostingRegressor
# from sklearn import linear_model
# from sklearn.ensemble import RandomForestClassifier
# from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
import datetime

# settings.toml を読み込む
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.toml")
with open(CONFIG_PATH, "rb") as f:
    _config = tomli.load(f)


###########################################################################
# 学習モデル作成
###########################################################################
def get_models(mdl):
    model = None

    # 学習データの読み込み
    df_train = pd.read_csv('data/training.csv',
                           dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})
    features = _config["features"]["features_1"]
    X_train = np.array(df_train[features])

    # タイム（ラベル）を設定
    finish_time = df_train['finish_time']
    y_train = []
    for t in finish_time:
        t_arr = t.split('.')
        y_train.append(float(t_arr[0])*60 + float(t_arr[1] + '.' + t_arr[2] ))
    y_train = np.array(y_train)

    print(mdl + "学習中...")
    # サポートベクターマシーン
    if mdl == 'svr':
        model = SVR(kernel='rbf', C=5000, epsilon=0.01, gamma=0.000001)
        # model = SVR(class_weight='balanced', kernel='rbf', C=15000, gamma=0.000001)
        model.fit(X_train, y_train)
    # 勾配ブースティング回帰ツリーモデル
    elif mdl == 'gbrt':
        model = GradientBoostingRegressor(loss='ls', learning_rate=0.05, n_estimators=120, max_depth=5,
                                               random_state=42)
        model.fit(X_train, y_train)

    if mdl == 's_svr' or mdl == 's_gbrt' or mdl == 's_mlp':
        # データの標準化
        std_scalar = StandardScaler()
        std_scalar.fit(X_train)
        X_train_std = std_scalar.transform(X_train)
        std_scalar_y = StandardScaler()
        std_scalar_y.fit(np.reshape(y_train, (-1, 1)))
        y_train_std = std_scalar_y.transform(np.reshape(y_train, (-1, 1))).ravel()

        # サポートベクターマシーン（標準化）
        if mdl == 's_svr':
            # model = SVR(kernel='rbf', C=1000, epsilon=0.01, gamma=0.0001)
            model = SVR(kernel='rbf', C=15000, epsilon=0.01, gamma=0.000001)
            model.fit(X_train_std, y_train_std)
        # 勾配ブースティング回帰ツリーモデル（標準化）
        elif mdl == 's_gbrt':
            # model = GradientBoostingRegressor(loss='ls', learning_rate=0.05, n_estimators=120, max_depth=5,
            #                nn                       random_state=42)
            model = GradientBoostingRegressor(loss='ls', learning_rate=0.2, n_estimators=100, max_depth=10,
                                              random_state=42)
            model.fit(X_train_std, y_train_std)


    joblib.dump(model, 'models/' + mdl + '_model.pkl')


###########################################################################
# 学習モデル作成 (2023.5.16ver)
###########################################################################
def get_models2(mdl):
    model = None
    # 学習データの読み込み
    df_train = pd.read_csv('data/training.csv',
                           dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})
    # features = _config["features"]["features_1"]
    # features = _config["features"]["features_2"]
    # features = _config["features"]["features_3"]
    features = _config["features"]["features_4"]
    X_train = np.array(df_train[features])

    # ラベルを設定
    # Ytrain_HorseWin = df_train['horse_win'].ravel()
    Ytrain_HorseRankTop3 = df_train['horse_rank_top_3'].ravel()
    y_train = Ytrain_HorseRankTop3
    # y_train = Ytrain_HorseWin

    print(mdl + "学習中...")
    # サポートベクターマシーン
    if mdl == 'svr':
        model = SVR(kernel='rbf', C=5000, epsilon=0.01, gamma=0.000001)
        # model = SVR(class_weight='balanced', kernel='rbf', C=15000, gamma=0.000001)
        model.fit(X_train, y_train)
    # 勾配ブースティング回帰ツリーモデル
    elif mdl == 'gbrt':
        model = GradientBoostingRegressor(loss='ls', learning_rate=0.05, n_estimators=120, max_depth=5,
                                               random_state=42)
        model.fit(X_train, y_train)
    elif mdl == 'LR':
        model = LogisticRegression(penalty='l2',  # 正則化項(L1正則化 or L2正則化が選択可能)
                                   dual=False,  # Dual or primal
                                   tol=0.001,  # 計算を停止するための基準値
                                   C=0.8,  # 正則化の強さ
                                   fit_intercept=True,  # バイアス項の計算要否
                                   intercept_scaling=1,  # solver=‘liblinear’の際に有効なスケーリング基準値
                                   class_weight=None,  # クラスに付与された重み
                                   random_state=None,  # 乱数シード
                                   solver='lbfgs',  # ハイパーパラメータ探索アルゴリズム
                                   max_iter=200,  # 最大イテレーション数
                                   multi_class='auto',  # クラスラベルの分類問題（2値問題の場合'auto'を指定）
                                   verbose=0,  # liblinearおよびlbfgsがsolverに指定されている場合、冗長性のためにverboseを任意の正の数に設定
                                   warm_start=False,  # Trueの場合、モデル学習の初期化に前の呼出情報を利用
                                   n_jobs=None,  # 学習時に並列して動かすスレッドの数
                                   l1_ratio=None  # L1/L2正則化比率(penaltyでElastic Netを指定した場合のみ)
                                   )
        model.fit(X_train, y_train)

    if mdl == 's_svr' or mdl == 's_gbrt' or mdl == 's_mlp':
        # データの標準化
        std_scalar = StandardScaler()
        std_scalar.fit(X_train)
        X_train_std = std_scalar.transform(X_train)

        # サポートベクターマシーン（標準化）
        if mdl == 's_svr':
            # model = SVR(kernel='rbf', C=1000, epsilon=0.01, gamma=0.0001)
            model = SVR(kernel='rbf', C=15000, epsilon=0.01, gamma=0.000001)
            # model = svm.SVC(class_weight='balanced', kernel='rbf', C=15000, gamma=0.000001)
            model.fit(X_train_std, y_train)
        # 勾配ブースティング回帰ツリーモデル（標準化）
        elif mdl == 's_gbrt':
            # model = GradientBoostingRegressor(loss='ls', learning_rate=0.05, n_estimators=120, max_depth=5,
            #                nn                       random_state=42)
            model = GradientBoostingRegressor(loss='ls', learning_rate=0.2, n_estimators=100, max_depth=10,
                                              random_state=42)
            model.fit(X_train_std, y_train)
        elif mdl == 's_mlp':
            model = MLPClassifier(solver='lbfgs', random_state=0, hidden_layer_sizes=100, max_iter=1000)
            model.fit(X_train_std, y_train)

    # joblib.dump(model, 'models/' + mdl + '_model.pkl')
    joblib.dump(model, 'models/' + mdl + '_model4.pkl')


###########################################################################
# メイン処理
###########################################################################
def main():
    print('説明変数:', _config["features"]["features_4"])
    t0 = datetime.datetime.now()
    get_models2('LR')
    # get_models2('s_gbrt')
    # get_models2('s_svr')
    # get_models2('s_mlp')
    t1 = datetime.datetime.now() - t0
    print('=> 計測結果：', t1)
    # get_models('s_gbrt')
    print("完了！")


if __name__ == '__main__':
    main()
