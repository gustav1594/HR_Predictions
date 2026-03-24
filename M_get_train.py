#
# 処理内容：訓練・テストデータの作成
# 作成日：2022/9/8
#
import pandas as pd
import seaborn
import datetime
import numpy as np
seaborn.set()


###########################################################################
# レースデータを分割
###########################################################################
def devide_data(df, pattern):
    id_list = []
    for id in df['race_id'].astype(str).values:
        if pattern == 1:
            if id[10:] <= '06':
                id_list.append(id)
        else:
            if id[10:] > '06':
                id_list.append(id)
    df_h = df[df['race_id'].isin(id_list)]

    return df_h


###########################################################################
# 距離を分類
###########################################################################
def set_distanceClass(distance):
    if distance <= 1400:
        return 'A'
    elif distance > 1400 and distance <= 1800:
        return 'B'
    elif distance > 1800 and distance <= 2200:
        return 'C'
    elif distance > 2200 and distance <= 2600:
        return 'D'
    elif distance > 2600:
        return 'E'


###########################################################################
# 正規化を行う関数の定義
###########################################################################
def min_max_p(p):
    #最小値の計算
    min_p = p.min()
    #最大値の計算
    max_p = p.max()
    if min_p == max_p:
        min_max_p = 0.5
    else:   #正規化の計算
        min_max_p = (p - min_p) / (max_p - min_p)
    return min_max_p


###########################################################################
# メイン
###########################################################################
# CSVの読み込み
print('レースデータを読み込み...')
# 過去レース
df_tmp1 = pd.read_csv('data/race_data.csv',
                      dtype={'クラス': 'str', '人気': 'str', '生産者ID': 'str'})
# 最新レース
df_tmp2 = pd.read_csv('data/race_data_new.csv')

# 過去レースと最新レースを連結
df = pd.concat([df_tmp1, df_tmp2])
df = df.reset_index(drop=True)
RECENT_LINE = len(df_tmp1) - 1  # 実施済みレースの最後のインデックス

# 列名の調整
df = df.rename(columns={
    '日付': 'date', 'レースID': 'race_id', 'レース名': 'race_name', '競馬場': 'course_name', '距離': 'race_distance',
    '着順': 'finishing_position', '枠番': 'draw', '馬番': 'horse_number', '馬名': 'horse_name',
    '性齢': 'horse_old', '斤量': 'actual_weight', '騎手': 'jockey', 'タイム': 'finish_time',
    '着差': 'length_behind_winner', '単勝': 'win_odds', '人気': 'popular', '馬体重': 'declared_horse_weight', '増減': 'updown',
    '調教師': 'trainer', 'クラス': 'race_class', 'タイプ': 'track', '状態': 'track_condition',
    '発走時刻': 'start_time', '気温': 'temperature',
    '馬ID': 'horse_id', '騎手ID': 'jockey_id', '調教師ID': 'trainer_id', '調教タイム': 'training_time',
    '調教コース': 'training_course', '調教評価': 'training_eval', '調教指数': 'training_point',
    '同コース同距離1着': 'CC_CD1', '同コース同距離2着': 'CC_CD2', '同コース同距離3着': 'CC_CD3', '同コース同距離着外': 'CC_CD4',
    '同距離1着': 'CD1', '同距離2着': 'CD2', '同距離3着': 'CD3', '同距離着外': 'CD4',
    '短距離1着': 'SD1', '短距離2着': 'SD2', '短距離3着': 'SD3', '短距離着外': 'SD4',
    '長距離1着': 'LD1', '長距離2着': 'LD2', '長距離3着': 'LD3', '長距離着外': 'LD4',
    '同コース同距離実績指数': 'CC_CD_point', '同距離指数': 'CD_point', '短距離指数': 'SD_point', '長距離指数': 'LD_point',
    'タイム指数MAX': 'time_index_max', 'タイム指数平均': 'time_index_ave', 'タイム指数距離MAX': 'time_index_dis',
    'タイム指数コースMAX': 'time_index_cou', '調子偏差値': 'condition_deviation',
    '種牡馬ID': 'stal_id', '種牡馬名': 'stal_name', '種牡馬指数': 'stal_point', '母父ID': 'stal2_id',
    '母父名': 'stal2_name', '母父指数': 'stal2_point', '血統指数': 'ped_point', '生産者ID': 'breeder_id',
    '生産者名': 'breeder_name', '生産者指数': 'breeder_point', '気候適性': 'climate',
    '出走頭数': 'runners', 'コーナー通過順': 'corner', '脚質': 'running_style'
})

# コースタイプ（0:芝、1:ダート）を振り分ける
track_list = []
print("コースタイプを振り分け...")
df['track'] = df['track'].apply(lambda x: '0' if x == '芝' else '1')

print("新しい項目を追加...")
# df['recent_6_runs'] = 'NA'
df['recent_ave_rank'] = 7
df['horse_index'] = 'NA'
df['jockey_index'] = 'NA'
df['trainer_index'] = 'NA'
df['jockey_ave_rank'] = 7
df['trainer_ave_rank'] = 7
df['actual_weight_nor'] = 0.5
df['timeindex_max_nor'] = 0.5
df['timeindex_ave_nor'] = 0.5
df['timeindex_dis_nor'] = 0.5
df['timeindex_cou_nor'] = 0.5
df['condition_deviation_nor'] = 0.5
df['training_point_nor'] = 0.5
df['horse_win'] = 0
df['horse_rank_top_3'] = 0
df['horse_rank_top_50_percent'] = 0

print("レース、馬、騎手、調教の各リストを作成...")
idx = 0
# レースID
race_ids = df['race_id'].drop_duplicates().to_list()
# 馬ID
id_list = df['horse_id'].drop_duplicates().to_list()
# 騎手ID
jockey_list = df['jockey_id'].drop_duplicates().to_list()
# 調教師ID
trainer_list = df['trainer_id'].drop_duplicates().to_list()

print("=> レースの数: ", len(race_ids))
print("=> 競争馬の数: ", len(id_list))
print("=> 騎手の数: ", len(jockey_list))
print("=> 調教師の数: ", len(trainer_list))

# 順位付け
print("1着と上位3着を設定...")
df['horse_win'] = df['finishing_position'].apply(lambda x: 1 if x == 1 else 0)
df['horse_rank_top_3'] = df['finishing_position'].apply(lambda x: 1 if x <= 3 else 0)

# レース距離を５分類にする
# df['distance_class'] = df['race_distance'].apply(set_distanceClass)

# 着外は一律'7'とする　→　逆効果なので削除
# df['finishing_position'] = df['finishing_position'].apply(lambda x: 7 if x >=4 else x)

# タイム指数と調子偏差値の正規化
t0 = datetime.datetime.now()
print("斤量とタイム指数と調子偏差値の正規化...")
# 欠損値への対応
# df.fillna({'time_index_max': 60, 'time_index_ave': 60, 'time_index_dis': 60, 'time_index_cou': 60}, inplace=True)
# df['time_index_ave'] = df['time_index_ave'].replace('-', 0)
# df['time_index_ave'] = df['time_index_ave'].astype(float)
for id in race_ids:
    df.loc[(df['race_id'] == id), 'actual_weight_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'actual_weight'])
    df.loc[(df['race_id'] == id), 'timeindex_max_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'time_index_max'])
    df.loc[(df['race_id'] == id), 'timeindex_ave_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'time_index_ave'])
    df.loc[(df['race_id'] == id), 'timeindex_dis_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'time_index_dis'])
    df.loc[(df['race_id'] == id), 'timeindex_cou_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'time_index_cou'])
    df.loc[(df['race_id'] == id), 'condition_deviation_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'condition_deviation'])
    df.loc[(df['race_id'] == id), 'training_point_nor'] = min_max_p(df.loc[(df['race_id'] == id), 'training_point'])

t1 = datetime.datetime.now() - t0
print('=> 計測結果：', t1)

# 馬の着順平均を計算
t0 = datetime.datetime.now()
print("馬の着順平均を計算...")
for id in id_list:
    df.loc[df['horse_id'] == id, 'horse_index'] = idx
    idx += 1

    # breaker = '/'
    # 馬の過去の成績を通算
    for track in ['0', '1']:
        recent = []
        for index, record in df[(df['horse_id'] == id) & (df['track'] == track)].iterrows():
            # 着順がない行は、最新平均ランクは据え置き
            if pd.isnull(record.finishing_position):
                pass
            else:
                # df.loc[index, 'recent_6_runs'] = breaker.join(str(recent))
                recent.append(record.finishing_position)
                if len(recent) > 3:
                    recent = recent[1:]

            if (len(recent)) != 0:
                df.loc[index, 'recent_ave_rank'] = sum(map(float, recent)) / float(len(recent))

    # 予想脚質を計算
    recent = []
    for index, record in df[df['horse_id'] == id].iterrows():
        # 脚質がない行の処理
        if pd.isnull(record.running_style):
            if len(recent) != 0:
                df.loc[index, 'running_style'] = sum(map(float, recent)) / float(len(recent))
            else:
                df.loc[index, 'running_style'] = 0
        else:
            recent.append(record.running_style)
            if len(recent) > 3:
                recent = recent[1:]

t1 = datetime.datetime.now() - t0
print('=> 計測結果：', t1)

# 騎手の着順平均を計算
t0 = datetime.datetime.now()
print("騎手の着順平均を計算...")
idx = max(idx, 30000)
for id in jockey_list:
    df.loc[df.jockey_id == id, 'jockey_index'] = idx
    idx += 1

    # 芝ダート、競馬場別に集計
    # for track in ['0', '1']:
    #    for course in ['札幌','函館','福島','新潟','東京','中山','中京','京都','阪神','小倉']:
    #        jockey_record =\
    #            df.loc[(df['jockey_id'] == id) & (df['track'] == track) & (df['course_name'] == course)]
    #        for index, record in jockey_record.iterrows():
    #            jockey_position = jockey_record.loc[df.finishing_position > 0, 'finishing_position']
    #            if len(jockey_position) != 0:
    #                df.loc[index, 'jockey_ave_rank'] =\
    #                    sum(map(float, jockey_position))/float(len(jockey_position))

    jockey_record = df.loc[df.jockey_id == id]
    jockey_position = jockey_record.loc[df.finishing_position > 0, 'finishing_position']
    if len(jockey_position) != 0:
        df.loc[df.jockey_id == id, 'jockey_ave_rank'] = \
            sum(map(float, jockey_position)) / float(len(jockey_position))

t1 = datetime.datetime.now() - t0
print('=> 計測結果：', t1)

# 調教師の着順平均を計算
print("調教師の着順平均を計算...")
t0 = datetime.datetime.now()
idx = max(idx, 40000)
for id in trainer_list:
    df.loc[df.trainer_id == id, 'trainer_index'] = idx
    idx += 1

    # 芝ダート、距離別に集計
    # for track in ['0', '1']:
    #    for distance in ['A','B','C','D','E']:
    #        trainer_record =\
    #            df.loc[(df['trainer_id'] == id) & (df['track'] == track) & (df['distance_class'] == distance)]
    #        for index, record in trainer_record.iterrows():
    #            trainer_position = trainer_record.loc[df.finishing_position > 0, 'finishing_position']
    #            if len(trainer_position) != 0:
    #                df.loc[index, 'trainer_ave_rank'] =\
    #                    sum(map(float, trainer_position))/float(len(trainer_position))

    trainer_record = df.loc[df.trainer_id == id]
    trainer_position = trainer_record.loc[df.finishing_position > 0, 'finishing_position']
    if len(trainer_position) != 0:
        df.loc[df.trainer_id == id, 'trainer_ave_rank'] = \
            sum(map(float, trainer_position)) / float(len(trainer_position))

t1 = datetime.datetime.now() - t0
print('=> 計測結果：', t1)

# 訓練データとテストデータの振り分け
print("訓練データとテストデータ作成...")
df_train = df.loc[df.index <= RECENT_LINE]
df_test = df.loc[df.index > RECENT_LINE]

# 欠損データを除外する
df_train = df_train.dropna(subset=['finishing_position'])
# 無効の行を削除する (2023.3.18)
df_test = df_test.drop(df_test[df_test['popular'] == '--'].index)

df_train.to_csv('data/training.csv')
df_test.to_csv('data/testing.csv')

print("完了!")
