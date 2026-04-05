#
# 処理内容：勝ち馬予測データの作成
# 作成日：2022/9/8
#
import M_common
import joblib
import re
import pandas as pd
import numpy as np
# from sklearn.svm import SVR
import datetime
from sklearn.preprocessing import StandardScaler
# import M_buy_ticket
import tomli
import os

# settings.toml を読み込む
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.toml")
with open(CONFIG_PATH, "rb") as f:
    _config = tomli.load(f)


###########################################################################
# CSVファイルへの書き込み
###########################################################################
# CSV書き込みver2
def write_csv(pred, y_pred, race_id, race_name, horse_number, horse_name, date, path, name):
    race_num = []
    # レース番号リストを作成
    for num in race_id:
        race_num.append(str(num)[-2:])

    columns = ['No.', 'Date', 'RaceID', 'RaceName', 'Num', 'HorseName', 'PredRank', 'ticket']
    # columns_all = ['No.', 'Date', 'RaceID', 'RaceName', 'Num', 'HorseName', 'PredRank', 'PredTime']
    df = pd.DataFrame({'No.': race_num, 'Date': date, 'RaceID': race_id, 'RaceName': race_name,
                       'Num': horse_number, 'HorseName': horse_name, 'PredRank': pred})

    # 全馬用データセット
    # df_all = df
    # df_all['PredTime'] = y_pred

    # 馬券の初期化
    df['ticket'] = ''

    # １～３位予想のみ抽出
    df = df.drop(df.index[df['PredRank'] >= 4])

    # ソート
    df = df.sort_values(['Date', 'No.', 'RaceID', 'PredRank'], ascending=[True, True, True, True])
    # df_all = df_all.sort_values(['Date', 'No.', 'RaceID', 'PredTime'], ascending=[True, True, True, False])

    # レースIDの分だけループ
    race_ids = df['RaceID'].drop_duplicates().to_list()
    for id in race_ids:
        # 馬券の設定
        num_lst = df.loc[df['RaceID'] == id, 'Num'].values

        ticket_lst = []
        # 1-2
        if num_lst[0] < num_lst[1]:
            ticket_lst.append(str(num_lst[0]) + "-" + str(num_lst[1]))
        else:
            ticket_lst.append(str(num_lst[1]) + "-" + str(num_lst[0]))

        # 2-3
        if num_lst[1] < num_lst[2]:
            ticket_lst.append(str(num_lst[1]) + "-" + str(num_lst[2]))
        else:
            ticket_lst.append(str(num_lst[2]) + "-" + str(num_lst[1]))

        # 1-3
        if num_lst[0] < num_lst[2]:
            ticket_lst.append(str(num_lst[0]) + "-" + str(num_lst[2]))
        else:
            ticket_lst.append(str(num_lst[2]) + "-" + str(num_lst[0]))

        # df.loc[(df['RaceID'] == id) & ((df['PredRank'] == 2) | (df['PredRank'] == 3)), 'ticket'] = ticket_lst
        df.loc[df['RaceID'] == id, 'ticket'] = ticket_lst

        # 予想タイムの１位との差異を設定
        # time_lst = df_all.loc[df_all['RaceID'] == id, 'PredTime'].values
        # time_tmp = time_lst[0]
        # df_all.loc[df_all['RaceID'] == id, 'Diff'] \
        #    = df_all.loc[df_all['RaceID'] == id, 'PredTime'].apply(lambda x: x - time_tmp)

    # 一着フラグが"1"のみ抽出
    # df_all = df_all.drop(df_all.index[df_all['PredTime'] == 0])

    df.to_csv("{0}/{1}_predictions.csv".format(path, name), index=False, sep=',', columns=columns)
    # df_all.to_csv("{0}/{1}_predictions_all.csv".format(path, name), index=False, sep=',', columns=columns_all)


###########################################################################
# CSVファイルへの書き込み 3
###########################################################################
# CSV書き込みver3
def write_csv2(y_pred, race_id, race_name, horse_number, horse_name, date, path, name):
    race_num = []

    # レース番号リストを作成
    for num in race_id:
        race_num.append(str(num)[-2:])

    columns = ['No.', 'Date', 'RaceID', 'RaceName', 'Num', 'HorseName', 'Pred', 'ticket']
    df = pd.DataFrame({'No.': race_num, 'Date':date, 'RaceID': race_id, 'RaceName': race_name,
                       'Num': horse_number, 'HorseName': horse_name})
    # レースIDリスト
    race_ids = df['RaceID'].drop_duplicates().to_list()

    # 全馬用データセット
    df['Pred'] = y_pred
    # 馬券の初期化
    df['ticket'] = ''

    # ソート
    df = df.sort_values(['Date', 'No.', 'RaceID', 'Pred'], ascending=[True, True, True, False])

    # 一着フラグが"1"のみ抽出
    # df = df.drop(df.index[df['Pred'] == 0])

    # LRの場合は前出走馬の確率を出力する
    if name == 'LR':
        # 以下、レースIDごとにループ
        for id in race_ids:
            prbblty = sum(df.loc[df['RaceID'] == id, 'Pred'].values)
            # print(prbblty)
            # 出走馬Numリスト
            horse_num = df.loc[df['RaceID'] == id, 'Num'].values
            # print(horse_num)
            horse_num = pd.Series(horse_num).drop_duplicates().to_list()
            # print(horse_num)
            if prbblty > 3:
                for run_num in horse_num:
                    df.loc[(df['RaceID'] == id) & (df['Num'] == run_num), 'Pred'] = (3 * df.loc[(df['RaceID'] == id) & (df['Num'] == run_num), 'Pred'].values) / prbblty

            # ticket_lst = []
            # df.loc[df['RaceID'] == id, 'ticket'] = ticket_lst
    else:
        # 以下、レースIDごとにループ
        for id in race_ids:
            # cnt = len(df.index[df['RaceID'] == id])
            # if cnt > 3:
            # df = df.drop(df.index[df['RaceID'] == id])
            # 上位３着のみ抽出
            df = df.drop(df.index[df['RaceID'] == id][3:])

            # 馬券の設定
            num_lst = df.loc[df['RaceID'] == id, 'Num'].values

            ticket_lst = []
            # 1-2
            if num_lst[0] < num_lst[1]:
                ticket_lst.append(str(num_lst[0]) + "-" + str(num_lst[1]))
            else:
                ticket_lst.append(str(num_lst[1]) + "-" + str(num_lst[0]))

            # 2-3
            if num_lst[1] < num_lst[2]:
                ticket_lst.append(str(num_lst[1]) + "-" + str(num_lst[2]))
            else:
                ticket_lst.append(str(num_lst[2]) + "-" + str(num_lst[1]))

            # 1-3
            if num_lst[0] < num_lst[2]:
                ticket_lst.append(str(num_lst[0]) + "-" + str(num_lst[2]))
            else:
                ticket_lst.append(str(num_lst[2]) + "-" + str(num_lst[0]))

            df.loc[df['RaceID'] == id, 'ticket'] = ticket_lst

    df.to_csv("{0}/{1}_predictions.csv".format(path, name), index=False, sep=',', columns=columns)

###########################################################################
# 無効になった馬の行を削除する
###########################################################################
def del_row(race_id):
    print('中止した馬の行を削除')
    # CSVの読み込み
    df = pd.read_csv('data/testing.csv',
                     dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})

    # 馬体重の取得
    url = f'https://race.netkeiba.com/race/shutuba.html?race_id={str(race_id)}'
    df_tmp = pd.read_html(url, header=0)[0]
    df_tmp = df_tmp.drop(index=0)

    # 除外された馬番を取得
    inv_num = df_tmp.loc[df_tmp['馬体重(増減)'] == '--', '馬番']

    # 無効の行を削除する (2023.3.18)
    df = df.drop(df[df['馬番'] == inv_num].index)

    # 保存する
    df.to_csv('data/testing.csv', index=0)

###########################################################################
# 馬体重の更新
###########################################################################
def update_weight(race_id):
    try:
        # CSVの読み込み
        df = pd.read_csv('data/testing.csv',
                         dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})

        # 馬体重の取得
        url = f'https://race.netkeiba.com/race/shutuba.html?race_id={str(race_id)}'
        df_tmp = pd.read_html(url, header=0)[0]
        df_tmp = df_tmp.drop(index=0)

        # 脱退などで取得できなかったものは除外する
        # for index, row in df_tmp.iterrows():
        #    if df_tmp['馬体重(増減)'][index] == '--':
        #        target = df.index[(df['horse_number'] == index) & (df['race_id'] == race_id)]
        #        df = df.drop(target)

        df_tmp.loc[df_tmp['馬体重(増減)'] == '--', '馬体重(増減)'] = np.nan
        df_tmp = df_tmp.dropna(subset=['馬体重(増減)'])
        df_tmp = df_tmp.reset_index()

        df_tmp['馬体重(増減)'] = df_tmp['馬体重(増減)'].apply(lambda x: re.sub(r'\(前計不\)', '(0)', x))

        weight_list = []
        updown_list = []
        for i in range(len(df_tmp)):
            weight_list.append(df_tmp['馬体重(増減)'][i][0:3])
            updown_list.append(re.findall('(?<=\().*(?=\))', df_tmp['馬体重(増減)'][i]))

        # testingデータに、更新された馬体重を書き込む
        df.loc[df['race_id'] == race_id, 'declared_horse_weight'] = weight_list
        df.loc[df['race_id'] == race_id, 'updown'] = updown_list

        print(df.loc[df['race_id'] == race_id, ['race_id', 'horse_name', 'declared_horse_weight', 'updown']])
        print('---------------------------------------------------------------------------')

        df.to_csv('data/testing.csv', index=0)
    except ValueError:
        print("該当のレースが存在しません。出直して下さい")
        exit()

###########################################################################
# 勝ち馬の予測データ作成
###########################################################################
def pred_win(mdl):
    y_pred = None
    # データ読み込み
    df_train = pd.read_csv('data/training.csv',
                          dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})
    df_test = pd.read_csv('data/testing.csv',
                          dtype={'popular': 'str', 'race_class': 'str', 'breeder_id': 'str'})
    # 説明変数
    # features = _config["features"]["features_1"]
    features = _config["features"]["features_4"]

    # 欠損データを取り除く
    df_train = df_train.dropna(subset=['finishing_position'])
    # df_test = df_test.dropna(subset=['declared_horse_weight'])
    df_test = df_test.reset_index(drop=True)

    X_train = np.array(df_train[features])
    X_test = np.array(df_test[features])

    print(mdl + "予測データ作成中...")
    if mdl == 'svr' or mdl == 'gbrt':
        model = joblib.load("./models/" + mdl + "_model.pkl")
        y_pred = model.predict(X_test)
    elif mdl == 's_svr' or mdl == 's_gbrt':
        # 標準化
        std_scalar = StandardScaler()
        std_scalar.fit(X_train)
        X_test_std = std_scalar.transform(X_test)

        # SVRモデル(標準化)の予測
        model = joblib.load("./models/" + mdl + "_model.pkl")
        y_pred = model.predict(X_test_std)
    elif mdl == 'LR':
        # model = joblib.load("./models/" + mdl + "_model.pkl")
        model = joblib.load("./models/" + mdl + "_model4.pkl")
        y_pred = model.predict_proba(X_test)

    # CSVに書き込む
    # top1, top3, top50 = M_common.Time_to_label(df_test, y_pred)
    # top1_int = top1.astype(int)
    # top3_int = top3.astype(int)
    # top50_int = top50.astype(int)
    # write_csv(top1_int, top3_int, top50_int,
    #          df_test.race_id, df_test.race_name,
    #          df_test.horse_number, df_test.horse_name,
    #          # 2023.2.14ADD S
    #          df_test.date,
    #          # 2023.2.14ADD E
    #          'predictions', mdl)

    # CSVに書き込むver2 (2023.3.7)
    # pred_rank = M_common.Time_to_rank(df_test, y_pred)
    # write_csv(pred_rank, y_pred,
    #          df_test.race_id, df_test.race_name,
    #          df_test.horse_number, df_test.horse_name,
    #          df_test.date,
    #          'predictions', mdl)

    # CSVに書き込むver3 (2023.5.19)
    if mdl == 'LR':
        write_csv2(y_pred[:,1],
                   df_test.race_id, df_test.race_name,
                   df_test.horse_number, df_test.horse_name,
                   df_test.date,
                   'predictions', mdl)
    else:
        write_csv2(y_pred,
                  df_test.race_id, df_test.race_name,
                  df_test.horse_number, df_test.horse_name,
                  df_test.date,
                  'predictions', mdl)

###########################################################################
# メイン処理
###########################################################################
def main():
    t_start = datetime.datetime.now()
    YEAR = t_start.year

    # レースIDリスト作成
    id_list = M_common.get_target_race_id_list(YEAR, YEAR)

    # 各レースの馬体重取得時刻
    time_list = _config["app"]["time_list"]

    print('---------------------------')
    print('0:   まとめてレースを予想')
    print('1:   タイマーモードで予想')
    print('2:   検証用レースを予想')
    print('---------------------------')
    select = input('モードを選択： ')

    # 予想データを作成する
    if select == '0':
        # pred_win('s_svr')
        # M_common.feedback('s_svr', 1)
        pred_win('s_gbrt')
        M_common.feedback('s_gbrt', 1)

        print("完了！")
    elif select == '1':
        pred_flag = False
        while True:
            t_now = datetime.datetime.now()
            t_str = str(t_now.hour).zfill(2) + str(t_now.minute).zfill(2)
            # 各レースの指定時刻で馬体重を取得し、レース予想を行う
            if (t_str in time_list) and (pred_flag == False):
                idx = time_list.index(t_str)
                race_id = []
                # 各競馬場の直近のレースIDを取得
                for i in range(len(M_common.PLACES)):
                    race_id.append(id_list[i][idx])

                # 馬体重の更新
                for i in range(len(M_common.PLACES)):
                    # del_row(int(race_id[i]))
                    update_weight(int(race_id[i]))

                # 勝ち馬の予想
                pred_win('s_svr')

                # チケットの購入
                # print('チケット購入待機中...')
                # time.sleep(5)
                # M_buy_ticket.main(str(int(idx) + 1))

                print("完了！")
                pred_flag = True
                # 最終レース時に処理を終了する
                if idx == 11:
                    break
            elif (t_str not in time_list) and (pred_flag == True):
                pred_flag = False
            # time.sleep(58)
    elif select == '2':
        t0 = datetime.datetime.now()
        print('計測開始：', t0)

        pred_win('LR')
        # pred_win('s_svr')
        # M_common.feedback('s_svr', 2)
        # M_common.feedback_umaren('s_svr', 2)
        # pred_win('s_gbrt')

        t1 = datetime.datetime.now() - t0
        print('=> 計測結果：', t1)
        print("完了！")
    else:
        print("終了...!")


if __name__ == '__main__':
    main()
