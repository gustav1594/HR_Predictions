#
# 処理内容：訓練・テストデータの作成
# 作成日：2022/9/8
# 更新日：2026/3/26 chatGPT修正版
#       1.for文やiterrows()などのループ処理の削減
#         →正規化はgroupby化、平均値計算はrolling化
#       2.メイン処理内のいくつかを関数に分割
#
import pandas as pd
# import seaborn
import datetime
# import numpy as np
# seaborn.set()
DEFAULT_RANK = 7
ZERO_RANK = 0
DEFAULT_NOR = 0.5
NORM_TARGETS = [
    'actual_weight',
    'time_index_max',
    'time_index_ave',
    'time_index_dis',
    'time_index_cou',
    'condition_deviation',
    'training_point',
]


###########################################################################
# レースデータを分割 ※現在、未使用
###########################################################################
# def divide_data(df, pattern):
#    id_list = []
#    for race_id in df['race_id'].astype(str).values:
#        if pattern == 1:
#            if race_id[10:] <= '06':
#                id_list.append(race_id)
#        else:
#            if race_id[10:] > '06':
#                id_list.append(race_id)
#    df_h = df[df['race_id'].isin(id_list)]
#
#    return df_h


###########################################################################
# 正規化を行う関数の定義
###########################################################################
def min_max_or_default(s: pd.Series, default: float = 0.5) -> pd.Series:
    s = pd.to_numeric(s, errors='coerce')
    mn = s.min()
    mx = s.max()
    if pd.isna(mn) or pd.isna(mx) or mn == mx:
        return pd.Series(default, index=s.index)
    return (s - mn) / (mx - mn)


###########################################################################
# csvデータの読み込み
###########################################################################
def load_data():
    # 過去レース
    df_tmp1 = pd.read_csv('data/race_data.csv',
                          dtype={'クラス': 'str', '人気': 'str', '生産者ID': 'str'})
    # 最新レース
    df_tmp2 = pd.read_csv('data/race_data_new.csv')

    # 過去レースと最新レースを連結
    recent_line = len(df_tmp1) - 1  # 実施済みレースの最後のインデックス
    df = pd.concat([df_tmp1, df_tmp2])
    df = df.reset_index(drop=True)

    # 列名の調整
    df = df.rename(columns={
        '日付': 'date', 'レースID': 'race_id', 'レース名': 'race_name', '競馬場': 'course_name',
        '距離': 'race_distance',
        '着順': 'finishing_position', '枠番': 'draw', '馬番': 'horse_number', '馬名': 'horse_name',
        '性齢': 'horse_old', '斤量': 'actual_weight', '騎手': 'jockey', 'タイム': 'finish_time',
        '着差': 'length_behind_winner', '単勝': 'win_odds', '人気': 'popular', '馬体重': 'declared_horse_weight',
        '増減': 'updown',
        '調教師': 'trainer', 'クラス': 'race_class', 'タイプ': 'track', '状態': 'track_condition',
        '発走時刻': 'start_time', '気温': 'temperature',
        '馬ID': 'horse_id', '騎手ID': 'jockey_id', '調教師ID': 'trainer_id', '調教タイム': 'training_time',
        '調教コース': 'training_course', '調教評価': 'training_eval', '調教指数': 'training_point',
        '同コース同距離1着': 'CC_CD1', '同コース同距離2着': 'CC_CD2', '同コース同距離3着': 'CC_CD3',
        '同コース同距離着外': 'CC_CD4',
        '同距離1着': 'CD1', '同距離2着': 'CD2', '同距離3着': 'CD3', '同距離着外': 'CD4',
        '短距離1着': 'SD1', '短距離2着': 'SD2', '短距離3着': 'SD3', '短距離着外': 'SD4',
        '長距離1着': 'LD1', '長距離2着': 'LD2', '長距離3着': 'LD3', '長距離着外': 'LD4',
        '同コース同距離実績指数': 'CC_CD_point', '同距離指数': 'CD_point', '短距離指数': 'SD_point',
        '長距離指数': 'LD_point',
        'タイム指数MAX': 'time_index_max', 'タイム指数平均': 'time_index_ave', 'タイム指数距離MAX': 'time_index_dis',
        'タイム指数コースMAX': 'time_index_cou', '調子偏差値': 'condition_deviation',
        '種牡馬ID': 'stal_id', '種牡馬名': 'stal_name', '種牡馬指数': 'stal_point', '母父ID': 'stal2_id',
        '母父名': 'stal2_name', '母父指数': 'stal2_point', '血統指数': 'ped_point', '生産者ID': 'breeder_id',
        '生産者名': 'breeder_name', '生産者指数': 'breeder_point', '気候適性': 'climate',
        '出走頭数': 'runners', 'コーナー通過順': 'corner', '脚質': 'running_style'
    })

    # コースタイプ（0:芝、1:ダート）を振り分ける
    # track_list = []
    print("コースタイプを振り分け...")
    TRACK_MAP = {'芝': 0, 'ダート': 1}
    df['track'] = df['track'].map(TRACK_MAP)

    # 日付型への変換
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    print("新しい項目を追加...")
    # df['recent_6_runs'] = 'NA'
    df['recent_ave_rank'] = DEFAULT_RANK
    df['jockey_ave_rank'] = DEFAULT_RANK
    df['trainer_ave_rank'] = DEFAULT_RANK
    df['actual_weight_nor'] = DEFAULT_NOR
    df['time_index_max_nor'] = DEFAULT_NOR
    df['time_index_ave_nor'] = DEFAULT_NOR
    df['time_index_dis_nor'] = DEFAULT_NOR
    df['time_index_cou_nor'] = DEFAULT_NOR
    df['condition_deviation_nor'] = DEFAULT_NOR
    df['training_point_nor'] = DEFAULT_NOR
    df['horse_win'] = ZERO_RANK
    df['horse_rank_top_3'] = ZERO_RANK
    # df['horse_rank_top_50_percent'] = ZERO_RANK

    return recent_line, df


###########################################################################
# csvファイルへ書き込み
###########################################################################
def save_to_file(recent_line, df):
    df_train = df.loc[df.index <= recent_line]
    df_test = df.loc[df.index > recent_line]

    # 欠損データを除外する
    df_train = df_train.dropna(subset=['finishing_position'])
    # 無効の行を削除する (2023.3.18)
    # df_test = df_test.drop(df_test[df_test['popular'] == '--'].index)
    df_test = df_test[df_test['popular'] != '--']

    df_train.to_csv('data/training.csv', index=False)
    df_test.to_csv('data/testing.csv', index=False)


###########################################################################
# メイン
###########################################################################
def main():
    print('レースデータを読み込み...')
    recent_line, df = load_data()
    df['horse_index'] = pd.factorize(df['horse_id'])[0]
    df['jockey_index'] = pd.factorize(df['jockey_id'])[0] + 30000
    df['trainer_index'] = pd.factorize(df['trainer_id'])[0] + 40000

    print("レース、馬、騎手、調教の各リストを作成...")
    # レースID、馬ID、騎手ID、調教師IDリスト
    print("=> レースの数: ", df['race_id'].nunique())
    print("=> 競争馬の数: ", df['horse_id'].nunique())
    print("=> 騎手の数: ", df['jockey_id'].nunique())
    print("=> 調教師の数: ", df['trainer_id'].nunique())

    # 順位付け
    print("1着と上位3着を設定...")
    df['horse_win'] = (df['finishing_position'] == 1).astype(int)
    df['horse_rank_top_3'] = (df['finishing_position'] <= 3).astype(int)

    # タイム指数と調子偏差値の正規化
    t0 = datetime.datetime.now()
    print("斤量とタイム指数と調子偏差値の正規化...")
    # 2026.3.26 group_by化
    for col in NORM_TARGETS:
        df[f'{col}_nor'] = df.groupby('race_id')[col].transform(min_max_or_default)
    t1 = datetime.datetime.now() - t0
    print('=> 計測結果：', t1)

    # 馬の着順平均を計算
    t0 = datetime.datetime.now()
    print("馬の着順平均を計算...")
    # 2026.3.26 直近3走の着順平均のrolling化
    df['finishing_position'] = pd.to_numeric(df['finishing_position'], errors='coerce')
    df['recent_ave_rank'] = (
        df.sort_values(['horse_id', 'track', 'date', 'race_id'])
        .groupby(['horse_id', 'track'])['finishing_position']
        .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
        .fillna(DEFAULT_RANK)
    )
    # 2026.3.26 脚質予想のrolling化
    df['running_style'] = pd.to_numeric(df['running_style'], errors='coerce')
    pred_style = (
        df.sort_values(['horse_id', 'date', 'race_id'])
        .groupby('horse_id')['running_style']
        .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    )
    df['running_style'] = df['running_style'].fillna(pred_style).fillna(0)
    t1 = datetime.datetime.now() - t0
    print('=> 計測結果：', t1)

    # 騎手の着順平均を計算
    t0 = datetime.datetime.now()
    print("騎手の着順平均を計算...")
    # 2026.3.26 騎手・調教師平均は「全期間平均」ではなく「その時点までの過去平均」にする
    df['jockey_ave_rank'] = (
        df.sort_values(['jockey_id', 'date', 'race_id'])
        .groupby('jockey_id')['finishing_position']
        .transform(lambda s: s.shift(1).expanding().mean())
        .fillna(DEFAULT_RANK)
    )
    t1 = datetime.datetime.now() - t0
    print('=> 計測結果：', t1)

    # 調教師の着順平均を計算
    print("調教師の着順平均を計算...")
    t0 = datetime.datetime.now()
    # 2026.3.26 騎手・調教師平均は「全期間平均」ではなく「その時点までの過去平均」にする
    df['trainer_ave_rank'] = (
        df.sort_values(['trainer_id', 'date', 'race_id'])
        .groupby('trainer_id')['finishing_position']
        .transform(lambda s: s.shift(1).expanding().mean())
        .fillna(DEFAULT_RANK)
    )
    t1 = datetime.datetime.now() - t0
    print('=> 計測結果：', t1)

    # 訓練データとテストデータの振り分け
    print("訓練データとテストデータ作成...")
    save_to_file(recent_line, df)
    print("完了!")


if __name__ == '__main__':
    main()
