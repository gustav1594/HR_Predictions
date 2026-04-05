from itertools import product
import re
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import os
import tomli
from os.path import join, dirname
from dotenv import load_dotenv
import time
from functools import wraps
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

###########################################################################
# 共通定数
###########################################################################
# 環境変数ファイルを読み込む
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# settings.toml を読み込む
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.toml")
with open(CONFIG_PATH, "rb") as f:
    _config = tomli.load(f)


# レース開催日を設定
# race_day_config = _config["race_day"]
PLACES = _config["target"]["places"]


###########################################################################
# 共有関数
###########################################################################
# レースURL
def get_url(type):
    if type == 'previous':
        return 'https://db.netkeiba.com/race/'
    elif type == 'new':
        return 'https://race.netkeiba.com/race/shutuba.html?race_id='


# 回数とレース日を取得
def get_target_race_schedules():
    result = []

    for place_name in _config["target"]["places"]:
        place_code = _config["race"][place_name]
        pairs = _config["race_pair"][place_name]["pairs"]

        result.append({
            "place_name": place_name,
            "place_code": place_code,
            "pairs": pairs,
        })

    return result


# レースIDリスト作成
def get_target_race_id_list(y_start, y_end, r_start=1, r_end=12):
    schedules = get_target_race_schedules()

    id_list = []

    for schedule in schedules:
        place_list = schedule["place_code"]
        pairs = schedule["pairs"]

        for year in range(y_start, y_end + 1):
            for place in place_list:
                for pair in pairs:
                    kai = pair["kaisu"]
                    day = pair["day"]

                    for r in range(r_start, r_end + 1):
                        race_id = (
                            str(year).zfill(4)
                            + str(place).zfill(2)
                            + str(kai).zfill(2)
                            + str(day).zfill(2)
                            + str(r).zfill(2)
                        )
                        id_list.append(race_id)

    return id_list


# 日付変換（yyyy年mm月dd日 → yyyymmdd）
def conv_date(text):
    date_y = re.findall(r'(\d+)年', text)[0]
    date_m = re.findall(r'(\d+)月', text)[0]
    date_d = re.findall(r'(\d+)日', text)[0]
    date = str(date_y).zfill(4) + str(date_m).zfill(2) + str(date_d).zfill(2)
    return date

# 走破タイムからTop1,Top3,Top50を設定
def Time_to_label(df_test, y_pred):
    # top1, top3, top50を初期化
    top1 = np.zeros(y_pred.shape)
    top3 = np.zeros(y_pred.shape)
    top50 = np.zeros(y_pred.shape)
    current_race_ID = df_test.loc[0].race_id    #1行目のレースID
    race_time = []
    indices = []
    #テストデータの行数分ループする
    for index, row in df_test.iterrows():
        #同一レースのタイムと添字を格納する
        if current_race_ID == row.race_id:
            race_time.append(y_pred[index])
            indices.append(index)
        #レースIDの切り替わり時、または最終行到達時にTOP1,TOP3,TOP50を設定する
        if current_race_ID != row.race_id or index == len(df_test) - 1 :
            index_array = [x for _, x in sorted(zip(race_time, indices))]
            top1[index_array[0]] = 1
            top3[index_array[0]] = 1
            top3[index_array[1]] = 1
            top3[index_array[2]] = 1
            size = len(index_array)
            count = 1
            for c in index_array:
                if count / size <= 0.5:
                    top50[c] = 1
                else:
                    break
                count += 1
            indices = [index]
            race_time = [y_pred[index]]
        current_race_ID = row.race_id
    return top1, top3, top50

# 走破タイムから順位を設定
def Time_to_rank(df_test, y_pred):
    rank = np.zeros(y_pred.shape)   # 順位リスト
    current_race_ID = df_test.loc[0].race_id    #1行目のレースID
    race_time = []
    indices = []
    #テストデータの行数分ループする
    for index, row in df_test.iterrows():
        #同一レースのタイムと添字を格納する
        if current_race_ID == row.race_id:
            race_time.append(y_pred[index])
            indices.append(index)
        #レースIDの切り替わり時、または最終行到達時にRANKを設定する
        if current_race_ID != row.race_id or index == len(df_test) - 1 :
            index_array = [x for _, x in sorted(zip(race_time, indices))]
            count = 0
            for c in index_array:
                rank[c] = count + 1
                count = count + 1
            indices = [index]
            race_time = [y_pred[index]]
        current_race_ID = row.race_id
    return rank

# レース結果を取得
def feedback(model, pattern):
    df_pred = pd.read_csv('predictions/' + model + '_predictions.csv')
    df_money = pd.read_csv('./data/race_money_wide.csv')
    df_pred = df_pred.reset_index(drop=True)
    df_pred['rank'] = ''
    #df_pred['bet'] = df_pred['PredRank'].apply(lambda x: 100 if x == 2 or x == 3 else 0)
    df_pred['bet'] = 100
    df_pred['money'] = 0

    print('順位付け中...')
    race_id = ''

    # 着順を設定する
    for index, row in tqdm(df_pred.iterrows(), total=len(df_pred)):
        try:
            if race_id != row.RaceID:
                url = 'https://race.netkeiba.com/race/result.html?race_id=' + str(row.RaceID) + '&rf=race_submenu'
                df_race = pd.read_html(url, header=0)[0]

            race_id = row.RaceID
            df_pred.loc[index, 'rank'] = df_race.loc[df_race['馬名'] == row.HorseName, '着順'].values

            # ワイド獲得金額を取得
            if pattern == 1:
                html = requests.get(url)
                html.encoding = "EUC-JP"
                soup = BeautifulSoup(html.text, "html.parser")
                texts = soup.find("table", attrs={"summary": "ワイド"}).find_all(
                    "tr", attrs={"class": "Wide"})[0].text
                info = re.findall(r'(\S+)', texts)

                wide_list = []
                if len(info) < 10:
                    money_list = info[7].split('円')
                    wide_list.append([str(info[1]) + '-' + str(info[2]), money_list[0]])
                    wide_list.append([str(info[3]) + '-' + str(info[4]), money_list[1]])
                    wide_list.append([str(info[5]) + '-' + str(info[6]), money_list[2]])
                else:
                    money_list = info[11].split('円')
                    wide_list.append([str(info[1]) + '-' + str(info[2]), money_list[0]])
                    wide_list.append([str(info[3]) + '-' + str(info[4]), money_list[1]])
                    wide_list.append([str(info[5]) + '-' + str(info[6]), money_list[2]])
                    wide_list.append([str(info[7]) + '-' + str(info[8]), money_list[3]])
                    wide_list.append([str(info[9]) + '-' + str(info[10]), money_list[4]])
            else:
                wide_list = eval(df_money.loc[df_money['race_id'] == row.RaceID, 'wide_list'].values[0])

            money = 0
            for i in range(len(wide_list)):
                if row.ticket == wide_list[i][0]:
                    money = wide_list[i][1]

            df_pred.loc[index, 'money'] = money

        except (ImportError, KeyError, ValueError):
            pass
        except IndexError:
            pass

    # ソート
    #df_pred = df_pred.sort_values(['No.', 'RaceID', 'HorseWin'], ascending=[True, True, False])

    # データフレームをCSVに書き込む
    df_pred.to_csv('./predictions/' + model + '_results.csv', index=False)

    return df_pred

# レース結果を取得（馬連）
def feedback_umaren(model, pattern):
    df_pred = pd.read_csv('predictions/' + model + '_predictions.csv')
    df_money = pd.read_csv('./data/race_money_umaren.csv')
    df_pred = df_pred.reset_index(drop=True)
    df_pred['rank'] = ''
    #['bet'] = df_pred['HorseWin'].apply(lambda x: 0 if x == 1 else 100)
    df_pred['bet'] = 100
    df_pred['money'] = 0

    print('順位付け中...')
    race_id = ''

    # 着順を設定する
    for index, row in tqdm(df_pred.iterrows(), total=len(df_pred)):
        try:
            if race_id != row.RaceID:
                url = 'https://race.netkeiba.com/race/result.html?race_id=' + str(row.RaceID) + '&rf=race_submenu'
                df_race = pd.read_html(url, header=0)[0]

            race_id = row.RaceID
            df_pred.loc[index, 'rank'] = df_race.loc[df_race['馬名'] == row.HorseName, '着順'].values[0]

            win_list = []
            if pattern == 1:
                html = requests.get(url)
                html.encoding = "EUC-JP"
                soup = BeautifulSoup(html.text, "html.parser")
                money_list = soup.find("tr", attrs={"class": "Umaren"}).find_all(
                    "td", attrs={"class": "Payout"})[0].text.split('円')
                del money_list[-1]

                texts = soup.find("tr", attrs={"class": "Umaren"}).find_all(
                    "td", attrs={"class": "Result"})[0].text
                num_list = re.findall(r'\w+', texts)
                if len(num_list) == 2:
                    win_list = [str(num_list[0]) + '-' + (num_list[1])]
                elif len(num_list) == 4:
                    win_list = [str(num_list[0]) + '-' + (num_list[1]), str(num_list[2]) + '-' + (num_list[3])]

            else:
                win_list = eval(df_money.loc[df_money['race_id'] == row.RaceID, 'win'].values[0])
                money_list = eval(df_money.loc[df_money['race_id'] == row.RaceID, 'money'].values[0])

            for i in range(len(win_list)):
                if str(row.ticket) == win_list[i]:
                    df_pred.loc[index, 'money'] = money_list[i]

        except (ImportError, KeyError, ValueError):
            pass
        except IndexError:
            pass

    # ソート
    #df_pred = df_pred.sort_values(['No.', 'RaceID', 'HorseWin'], ascending=[True, True, False])

    # データフレームをCSVに書き込む
    df_pred.to_csv('./predictions/' + model + '_results_umaren.csv', index=False)

    return df_pred

# 競馬場　⇔　IDの変換
def get_courseName(id):
    course_num = str(id)[4:6]
    if course_num == '01':
        return '札幌'
    elif course_num == '02':
        return '函館'
    elif course_num == '03':
        return '福島'
    elif course_num == '04':
        return '新潟'
    elif course_num == '05':
        return '東京'
    elif course_num == '06':
        return '中山'
    elif course_num == '07':
        return '中京'
    elif course_num == '08':
        return '京都'
    elif course_num == '09':
        return '阪神'
    elif course_num == '10':
        return '小倉'

def get_courseID(name):
    if name == '札幌':
        return '01'
    elif name == '函館':
        return '02'
    elif name == '福島':
        return '03'
    elif name == '新潟':
        return '04'
    elif name == '東京':
        return '05'
    elif name == '中山':
        return '06'
    elif name == '中京':
        return '07'
    elif name == '京都':
        return '08'
    elif name == '阪神':
        return '09'
    elif name == '小倉':
        return '10'

###########################################################################
# 調教コースの基準値を取得
###########################################################################
def get_TrainingBasis(course):
    try:
        if "坂" in course:
            if "栗" in course:
                basis = 1.0014
            else:
                basis = 1.0
        else:
            if "南Ｗ" in course:
                basis = 1.0182
            elif "美Ｐ" in course:
                basis = 1.0470
            elif "北Ｃ" in course:
                basis = 1.0214
            elif "南Ｄ" in course:
                basis = 1.0308
            elif "南芝" in course:
                basis = 1.0739
            elif "ＣＷ" in course:
                basis = 1.0388
            elif "ＤＰ" in course:
                basis = 1.0774
            elif "栗Ｂ" in course:
                basis = 1.0552
            elif "栗芝" in course:
                basis = 1.0844
            elif "栗Ｅ" in course:
                basis = 1.0670
            elif "函Ｗ" in course:
                basis = 1.0105
            elif "函ダ" in course:
                basis = 1.0151
            elif "函芝" in course:
                basis = 1.0809
            elif "札ダ" in course:
                basis = 1.0198
            elif "札芝" in course:
                basis = 1.0774
            elif "小ダ" in course:
                basis = 1.0121
            elif "栗飛" in course:
                basis = 1.0014
            elif "阪ダ" in course:
                basis = 1.0121
            elif "小芝" in course:
                basis = 1.0121
            elif "小障" in course:
                basis = 1.0014
            elif "新ダ" in course:
                basis = 1.0121
            elif "新芝" in course:
                basis = 1.0774
            elif "南ダ" in course:
                basis = 1.0308
            elif "北Ｂ" in course:
                basis = 1.0214
            else:
                basis = 1.0
    except TypeError:
        basis = 1.0

    return basis

###########################################################################
# 最新の気温を取得
###########################################################################
def get_temp_new(place, hmin):
    if place == '札幌':
        block = '1/2/1400/1100'
    elif place == '函館':
        block = '1/4/2300/1202'
    elif place == '福島':
        block = '2/10/3610/7201'
    elif place == '中山':
        block = '3/15/4510/12204'
    elif place == '東京':
        block = '3/16/4410/13206'
    elif place == '新潟':
        block = '4/18/5410/15100'
    elif place == '中京':
        block = '5/26/5110/23100'
    elif place == '京都':
        block = '6/29/6110/26100'
    elif place == '阪神':
        block = '6/31/6310/28100'
    else:
        block = '9/43/8220/40100'

    url = 'https://tenki.jp/forecast/' + block + '/1hour.html'
    df = pd.read_html(url, encoding='utf-8', header=0)[0]

    column = df.columns[1] + '.' + str(int(hmin[0:2])-1)
    # 指定した時刻の気温を取得
    temp = df.loc[4, column]

    return float(temp)

# 2026.3.26追加
###########################################################################
# リトライ処理
###########################################################################
def get_with_retry(session, url, headers=None, timeout=10.0, max_retries=5, wait_seconds=1):
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=timeout, headers=headers)
            if session is None:
                raise RuntimeError("session not initialized")
            response.raise_for_status()
            return response

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.RequestException) as e:
            last_exception = e

            if attempt < max_retries:
                time.sleep(wait_seconds)
            else:
                print(f"通信失敗: {url} / {type(e).__name__}: {e}")
                raise

    raise last_exception

# 2026.3.26追加
###########################################################################
# Seleniumデコレータ対応
###########################################################################
def retry_on_selenium_error(max_retries=5, wait_seconds=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except (TimeoutException, StaleElementReferenceException) as e:
                    last_exception = e

                    if attempt < max_retries:
                        time.sleep(wait_seconds)
                    else:
                        print(f"{func.__name__} failed: {type(e).__name__}: {e}")
                        raise

            raise last_exception

        return wrapper
    return decorator

