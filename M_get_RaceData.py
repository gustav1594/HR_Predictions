#
# 処理内容：レースデータを作成 ver 2.0
# 作成日：2022/9/8
# 更新日：2026/3/26 chatGPT修正版
#       1.リトライ処理を共通関数get_with_retryに集約
#       2.例外処理(exception)の統一化
#       3.ログイン処理等の関数化※import時の実行を防ぐため
#       4.組み込み表記の回避(type, strなど)
#       5.設定値はTOMLファイルに移行
#
import os
import M_common
import re
import pandas as pd
from tqdm import tqdm
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
import numpy as np
import datetime
import math
import logging
import tomli
# from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
# from selenium.webdriver.remote.webdriver import WebDriver
# from requests import Session
# selenium 4
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service as ChromeService
# 'webdriver_manager’をインストールする$ pip3 install webdriver_manager
# from webdriver_manager.chrome import ChromeDriverManager

# パスを通すためのコード
# chromedriverを手動でインストールするコマンドはこちらから（https://pypi.org/project/chromedriver-binary/#history）
# ※chromのバージョンとdriverを揃える
# バージョンを指定したインストールpip install chromedriver-binary==125.0.6422.141
# == で指定するバージョンは各自がインストールしているChromeブラウザのバージョンにより異なるので、
# Chrome > Help > About Google Chrome から確認してください。
# import chromedriver_binary

logging.basicConfig(level=logging.INFO)

# settings.toml を読み込む
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.toml")
with open(CONFIG_PATH, "rb") as f:
    _config = tomli.load(f)


# 定義値
WEIGHT_FLAG = 0         # 馬体重の取得有無（0:なし 1:あり）
DEFAULT_TIME = 67.0     # 調教タイム（デフォルト値）
DEFAULT_POINT = 7.0     # 血統指数（デフォルト値）
DEFAULT_TIMEINDEX = 70  # スピード指数（デフォルト値）
TODAY = 0
DISTANCE_1400 = 1400
DISTANCE_1800 = 1800
DISTANCE_2200 = 2200
DISTANCE_2600 = 2600
TEMP_12 = 12.0
TEMP_18 = 18.0
TEMP_25 = 25.0
TEMP_30 = 30.0
headers = {'user-agent': _config["netkeiba"]["user_agent"]}     # アクセス拒否対応 2024.11.10


# 2026.3.26 関数化
###########################################################################
# Chromeドライバ生成
###########################################################################
def create_driver():
    options = webdriver.ChromeOptions()

    # バックグラウンド処理
    options.add_argument('--headless')
    sample_driver = Chrome(options=options)
    return sample_driver


# 2026.3.26 関数化
###########################################################################
# セッション開始
###########################################################################
def create_session():
    # セッション開始
    session = requests.session()
    session.headers.update(headers)
    retries = Retry(total=5,  # リトライ回数
                    backoff_factor=1,  # sleep時間
                    status_forcelist=[500, 502, 503, 504])  # timeout以外でリトライするステータスコード
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


# 2026.3.26 環境変数ファイルを追加、関数化
###########################################################################
# 初期化
###########################################################################
def initialize_netkeiba():
    global session, sample_driver
    session = create_session()
    sample_driver = create_driver()
    login_netkeiba(sample_driver)


# 2026.3.26 環境変数ファイルを追加、関数化
###########################################################################
# ログイン
###########################################################################
def login_netkeiba(login_driver):
    user_id = os.environ.get("USER")
    password = os.environ.get("PASS")
    # login_info = os.environ.get("login_info")
    url_login = 'https://regist.netkeiba.com/account/?pid=login&action=auth'
    # res_login = session.post(url_login, data=login_info)

    # ログイン
    login_driver.get(url_login)  # ログイン画面に接続
    login_id = login_driver.find_element(By.NAME, "login_id")
    login_pass = login_driver.find_element(By.NAME, "pswd")
    login_id.clear()
    login_pass.clear()
    login_id.send_keys(user_id)
    login_pass.send_keys(password)
    login_driver.find_element(By.XPATH, "/html/body/div[1]/div/div/form/div/div[1]/input").click()


# 2026.3.26 関数化
###########################################################################
# CSVファイルへ書き込み
###########################################################################
def write_csv(first_loop, df, filename):
    # データフレームをCSVに書き込む
    if first_loop:
        df.to_csv(filename, index=False)
        first_loop = False
    else:
        df.to_csv(filename, mode='a', header=False, index=False)
    return first_loop

# 2026.3.26 関数化
###########################################################################
# Soupの読み込み
###########################################################################
def fetch_page_soup(url):
    html = M_common.get_with_retry(session, url, timeout=10.0)
    html.encoding = "EUC-JP"

    soup = BeautifulSoup(html.text, "html.parser")
    return soup


###########################################################################
# 馬・騎手・調教師IDリストの作成
###########################################################################
def get_id(soup, keyword, race_type):
    id_list = []
    a_list = []
    if race_type == 'previous':
        a_list = soup.find("table", attrs={"summary": "レース結果"}).find_all(
            "a", attrs={"href": re.compile("^/" + keyword)}
        )
    elif race_type == 'new':
        a_list = soup.find("div", attrs={"class": "RaceTableArea"}).find_all(
            "a", attrs={"href": re.compile(".*/" + keyword + "/")}
        )
    for a in a_list:
        race_id = re.findall(r"\d+", a["href"])
        id_list.append(race_id[0])
    return id_list


###########################################################################
# 調教評価のポイント変換
###########################################################################
def get_training_point(ev_str):
    sign = ['A', 'B', 'C', 'D', 'E']
    p = [0.75, 0.775, 0.8, 0.9, 1.0]
    point = 1.0
    for i in range(5):
        if ev_str == sign[i]:   point = p[i]
    return point


###########################################################################
# ソースコード内のテキスト取得
###########################################################################
def get_sourceTexts(soup, race_type):
    texts = ''
    if race_type == 'previous':
        texts = (
                soup.find("div", attrs={"class": "data_intro"}).find_all("p")[0].text
                + soup.find("div", attrs={"class": "data_intro"}).find_all("p")[1].text
        )
    elif race_type == 'new':
        texts = soup.find("h1", attrs={"class": "RaceName"}).text
        for i in range(2):
            texts = texts + soup.find(
                # "div", attrs={"class": "RaceList_NameBox"}).find_all("span")[i].text
                "div", attrs={"class": "RaceList_NameBox"}).find_all("div")[i].text
    return texts

###########################################################################
# 過去レースの調教タイム取得
###########################################################################
def get_training_time(horse_id, race_id):
    training_time = DEFAULT_TIME   # 調教タイム
    val = 'E'                      # 調教評価
    crs = ''                       # 調教コース
    time_p = DEFAULT_TIME          # 調教指数

    url_tt = f'https://db.netkeiba.com/?pid=horse_training&id={horse_id}&rid={race_id}'

    # 通信エラーはデコレータ側でリトライ
    res_tt = M_common.get_with_retry(session, url_tt, timeout=10.0)

    try:
        soup_tt = BeautifulSoup(res_tt.content, "html.parser")
        df_tt = pd.read_html(res_tt.content)[0]

        # 調教評価・調教コース
        val = df_tt['評価.1'][0]
        crs = df_tt['コース'][0]
        crs_bln = df_tt['コース'].isnull()[0]

        # コース欠損時はデフォルト返却
        if crs_bln:
            return pd.Series({
                'time': training_time,
                'val': val,
                'crs': crs,
                'time_p': time_p
            })

        # 調教情報取得
        table = soup_tt.find("table", attrs={"summary": "調教タイム"})
        if table is None:
            return pd.Series({
                'time': training_time,
                'val': val,
                'crs': crs,
                'time_p': time_p
            })

        text_tt = table.find_all("li")

        # 調教タイムリスト
        tt_list = []
        for t in text_tt:
            tt = re.findall(r'>(.*)<', str(t))
            tt_list.append(tt)

        # 4Fと1Fの調教タイムの合計値を取得
        # 坂以外は左から3番目と5番目
        if "坂" in crs:
            training_time = round(
                (float(tt_list[1][0]) + float(tt_list[4][0])) * M_common.get_TrainingBasis(crs),
                2
            )
        else:
            training_time = round(
                (float(tt_list[2][0]) + float(tt_list[4][0])) * M_common.get_TrainingBasis(crs),
                2
            )

        # 調教指数算出
        point = get_training_point(val)
        time_p = round(training_time * point, 3)

    except (AttributeError, ValueError, IndexError, ImportError, KeyError) as e:
        logging.info(f"get_training_time parse error: race_id={race_id}, horse_id={horse_id}, {type(e).__name__}: {e}")

    return pd.Series({
        'time': training_time,
        'val': val,
        'crs': crs,
        'time_p': time_p
    })


###########################################################################
# 最新レースの調教タイム取得
###########################################################################
def get_training_time_new(race_id):
    url_tt = f"https://race.netkeiba.com/race/oikiri.html?race_id={race_id}&rf=race_submenu"

    try:
        # 2026.3.26リトライ処理追加
        res_tt = M_common.get_with_retry(session, url_tt, timeout=10.0)

        soup_tt = BeautifulSoup(res_tt.content, "html.parser")
        df_tt = pd.read_html(res_tt.content)[0]

        table = soup_tt.find("table", attrs={"id": "All_Oikiri_Table"})
        if table is None:
            raise ValueError("All_Oikiri_Table が見つかりません")

        text_tt = table.find_all("ul", attrs={"class": "TrainingTimeDataList"})

        df_bln = df_tt["コース"].isnull()
        course_list = df_tt["コース"]

        result = []

        for i in range(len(df_tt)):
            if df_bln[i]:
                result.append([DEFAULT_TIME, 'E', '', DEFAULT_TIME])
                continue

            if '計' in str(df_tt['調教タイム ラップ表示'][i]):
                result.append([DEFAULT_TIME, 'E', '', DEFAULT_TIME])
                continue

            tt = re.findall(r'(\d+\.\d+)|-', str(text_tt[i]))

            if "坂" in course_list[i] and "門" not in course_list[i]:
                training_time = round(
                    (float(tt[1]) + float(tt[7])) * M_common.get_TrainingBasis(course_list[i]), 2
                )
            elif len(tt) == 10:
                training_time = round(
                    (float(tt[4]) + float(tt[8])) * M_common.get_TrainingBasis(course_list[i]), 2
                )
            elif len(tt) == 9:
                training_time = round(
                    (float(tt[3]) + float(tt[7])) * M_common.get_TrainingBasis(course_list[i]), 2
                )
            elif len(tt) == 8:
                training_time = round(
                    (float(tt[2]) + float(tt[6])) * M_common.get_TrainingBasis(course_list[i]), 2
                )
            else:
                training_time = DEFAULT_TIME

            time_p = round(training_time * get_training_point(df_tt['評価.1'][i]), 3)

            result.append([
                training_time,
                df_tt['評価.1'][i],
                df_tt['コース'][i],
                time_p
            ])

        return result

    except (ValueError, IndexError, AttributeError) as e:
        logging.info(f"get_training_time_new 失敗 race_id={race_id}: {type(e).__name__}: {e}")
        return []


###########################################################################
# 過去レースの実績取得
###########################################################################
@M_common.retry_on_selenium_error(max_retries=5, wait_seconds=1)
def get_past_race(race_id, horse_num):
    url_tt = f'https://race.netkeiba.com/race/newspaper.html?m=riot-racedetail-past5-data&race_id={race_id}'
    sample_driver.get(url_tt)

    WebDriverWait(sample_driver, 15).until(
        ec.presence_of_element_located((By.CLASS_NAME, 'DataCellWrap01'))
    )

    result = []
    target_horse_num = horse_num + 2

    els_path = '/html/body/div[1]/div[5]/div[2]/div/div[3]/riot-racedetail-past5-data/div/div[2]/table/tbody/tr['

    ROW_MAP = {
        "CRCD": 1,
        "SD": 2,
        "CD": 3,
        "LD": 4,
    }

    # 各要素のパスを設定
    def els_lambda(x, y, z):
        return sample_driver.find_elements(
            By.XPATH,
            els_path + str(x) + ']/td[8]/table/tbody/tr[' + str(y) + ']/td[' + str(z) + ']'
        )

    # 4値の加重平均値を返す
    def ave_lambda(x1, x2, x3, x4):
        if x1 != 0 or x2 != 0 or x3 != 0 or x4 != 0:
            return np.average([1, 2, 3, 7], weights=[x1, x2, x3, x4])
        return DEFAULT_POINT

    # elementsから馬IDを取得
    def get_horse_id(elements):
        for el in elements:
            horse_href = el.get_attribute("href")
            m = re.search(r'https://db.netkeiba.com/horse/(.*)/', horse_href)
            if m:
                return m.group(1)
        return ''

    # 4値を返す
    def get_four_values(i, row_no, els_lambda):
        els_list = [els_lambda(i, row_no, col) for col in range(2, 6)]

        if any(len(els) == 0 for els in els_list):
            return [0, 0, 0, 0]

        return [int(els[0].text) for els in els_list]

    # 平均値を返す
    def get_average(values, ave_lambda, default_point):
        if all(v == 0 for v in values):
            return default_point
        return ave_lambda(*values)

    # 各elementsから馬の成績を取得
    try:
        for i in range(2, target_horse_num):
            horse_id_els = sample_driver.find_elements(
                By.XPATH,
                els_path + str(i) + ']/td[5]/dl/dt[2]/a'
            )
            if not horse_id_els:
                continue

            horse_IDs = get_horse_id(horse_id_els)

            scores = {
                key: get_four_values(i, row_no, els_lambda)
                for key, row_no in ROW_MAP.items()
            }

            pastrace_p = get_average(scores["CRCD"], ave_lambda, DEFAULT_POINT)
            pastCDrace_p = get_average(scores["CD"], ave_lambda, DEFAULT_POINT)
            pastSDrace_p = get_average(scores["SD"], ave_lambda, DEFAULT_POINT)
            pastLDrace_p = get_average(scores["LD"], ave_lambda, DEFAULT_POINT)

            result.append([
                horse_IDs,
                *scores["CRCD"],
                *scores["CD"],
                *scores["SD"],
                *scores["LD"],
                pastrace_p, pastCDrace_p, pastSDrace_p, pastLDrace_p
            ])

        return result

    except ZeroDivisionError as e:
        logging.info(f'get_past_race calculation error: race_id={race_id}, {type(e).__name__}: {e}')
        return []
    except (ValueError, IndexError, AttributeError) as e:
        logging.info(f'get_past_race parse error: race_id={race_id}, {type(e).__name__}: {e}')
        return []


###########################################################################
# タイム指数を取得
###########################################################################
@M_common.retry_on_selenium_error(max_retries=5, wait_seconds=1)
def get_timeindex(race_id, horse_num):
    def get_average_value(url):
        sample_driver.get(url)
        WebDriverWait(sample_driver, 15).until(
            ec.presence_of_element_located((By.CLASS_NAME, 'Average'))
        )

        average_els = sample_driver.find_elements(
            By.XPATH,
            '/html/body/div[1]/div[3]/div[4]/p[2]/strong'
        )

        if not average_els:
            return 0

        value = average_els[0].text
        return 0 if value == '-' else int(value.replace('*', ''))

    def parse_index_value(elements, default_value):
        if not elements:
            return default_value

        value = elements[0].text
        if value == '-':
            return default_value

        return int(value.replace('*', ''))

    ave_max = get_average_value(
        f'https://race.netkeiba.com/race/speed.html?race_id={race_id}&type=rank&mode=max#d'
    )
    ave_ave = get_average_value(
        f'https://race.netkeiba.com/race/speed.html?race_id={race_id}&type=rank&mode=average#d'
    )
    ave_dis = get_average_value(
        f'https://race.netkeiba.com/race/speed.html?race_id={race_id}&type=rank&mode=distance#d'
    )
    ave_cou = get_average_value(
        f'https://race.netkeiba.com/race/speed.html?race_id={race_id}&type=rank&mode=course#d'
    )

    url_tt = f'https://race.netkeiba.com/race/speed.html?race_id={race_id}&rf=shutuba_submenu'
    sample_driver.get(url_tt)

    WebDriverWait(sample_driver, 15).until(
        ec.presence_of_element_located((By.CLASS_NAME, 'list'))
    )

    result = []
    target_horse_num = horse_num + 1
    els_path = '/html/body/div[1]/div[3]/div[4]/table/tbody/tr['

    try:
        for i in range(1, target_horse_num):
            horse_IDels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[4]/a')
            timeindex_maxels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[8]/a')
            timeindex_aveels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[9]')
            timeindex_disels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[10]/a')
            timeindex_couels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[11]/a')

            if len(horse_IDels) == 0:
                continue

            horse_href = horse_IDels[0].get_attribute("href")
            m = re.search(r'https://db.netkeiba.com/horse/(.*)', horse_href)
            if not m:
                continue

            horse_id = m.group(1).replace('/', '')

            timeindex_max = parse_index_value(timeindex_maxels, ave_max)
            timeindex_ave = parse_index_value(timeindex_aveels, ave_ave)
            timeindex_dis = parse_index_value(timeindex_disels, ave_dis)
            timeindex_cou = parse_index_value(timeindex_couels, ave_cou)

            result.append([
                horse_id,
                timeindex_max,
                timeindex_ave,
                timeindex_dis,
                timeindex_cou
            ])

        return result

    except (ValueError, IndexError, AttributeError) as e:
        logging.info(f'get_timeindex parse error: race_id={race_id}, {type(e).__name__}: {e}')
        return []


###########################################################################
# 調子偏差値を取得
###########################################################################
@M_common.retry_on_selenium_error(max_retries=5, wait_seconds=1)
def get_conditiondeviation(race_id, horse_num):
    url_tt = f'https://race.sp.netkeiba.com/barometer/score.html?race_id={race_id}&rf=rs'
    sample_driver.get(url_tt)

    WebDriverWait(sample_driver, 15).until(
        ec.presence_of_element_located((By.CSS_SELECTOR, '.Shutuba_HorseList.BaroTableArea'))
    )

    result = []
    horse_count = horse_num + 1

    base_xpath = '/html/body/div[1]/div/div[8]/table/tbody/tr['

    try:
        for i in range(1, horse_count):
            horse_id_els = sample_driver.find_elements(
                By.XPATH,
                base_xpath + str(i) + ']/td[3]/dl/dt/a'
            )
            condition_deviation_els = sample_driver.find_elements(
                By.XPATH,
                base_xpath + str(i) + ']/td[4]/span[1]'
            )

            if len(horse_id_els) == 0:
                continue

            horse_href = horse_id_els[0].get_attribute("href")
            m = re.search(r'horse_id=(.*)&race_id', horse_href)
            if not m:
                continue

            horse_id = m.group(1)

            if len(condition_deviation_els) == 0:
                condition_deviation = 0
            else:
                condition_deviation = int(condition_deviation_els[0].text)

            result.append([horse_id, condition_deviation])

        return result

    except (ValueError, IndexError, AttributeError) as e:
        logging.info(f'get_conditiondeviation parse error: race_id={race_id}, {type(e).__name__}: {e}')
        return []


###########################################################################
# 種牡馬データを取得
###########################################################################
def get_stallion(horse_id, distance, track, race_type):
    # 種牡馬データを読み込む
    file_name = 'data/horse_ped.csv' if race_type == 1 else 'data/horse_ped2.csv'

    stallion_id = ''
    stallion_name = ''
    stallion_point = DEFAULT_POINT

    try:
        df = pd.read_csv(file_name)
        horse_id_str = str(horse_id)

        matched = df.loc[df['horse_id'].astype(str) == horse_id_str]

        # CSVに存在する場合
        if not matched.empty:
            stallion_id = matched.iloc[0]['stal_id']
            stallion_name = matched.iloc[0]['stal_name']

        # CSVに存在しない場合、サイトから取得
        else:
            url = f'https://db.netkeiba.com/horse/{horse_id}'
            soup = fetch_page_soup(url)
            pedigree_table = soup.find("table", attrs={"summary": re.compile(r'血統表')})
            if pedigree_table is None:
                raise ValueError("血統表テーブルが見つかりません")

            texts = pedigree_table.find_all(
                "a",
                attrs={"href": re.compile(r"^/horse")}
            )

            id_list = []
            for a in texts:
                match_id = re.findall(r'^/horse/ped/(\w+)', a["href"])
                if match_id:
                    id_list.append(match_id[0])

            family_list = []
            for a in texts:
                name = re.findall(r'>(.*)<', str(a))
                if name:
                    family_list.append(name[0])

            target_index = 0 if race_type == 1 else 4

            if len(id_list) <= target_index or len(family_list) <= target_index:
                raise IndexError("種牡馬情報の取得位置が不正です")

            stallion_id = id_list[target_index]
            stallion_name = family_list[target_index]

            df_ped = pd.DataFrame({
                'horse_id': [horse_id],
                'stal_id': [stallion_id],
                'stal_name': [stallion_name],
                'money': ['']
            })

            columns = ['horse_id', 'stal_id', 'stal_name', 'money']
            df_ped.to_csv(
                file_name,
                mode='a',
                header=False,
                index=False,
                sep=',',
                columns=columns
            )

        # 種牡馬の産駒成績取得
        url_stal = f'https://db.netkeiba.com/?pid=horse_sire&id={stallion_id}&course=1&mode=1&type=2'
        res_stal = M_common.get_with_retry(requests, url_stal, timeout=10.0)
        res_stal.encoding = res_stal.apparent_encoding

        html_tables = pd.read_html(res_stal.text, header=0)
        df_stal = html_tables[0] if track == '芝' else html_tables[1]

        if distance <= DISTANCE_1400:
            col_name = f'-1400({track})'
        elif distance <= DISTANCE_1800:
            col_name = f'-1800({track})'
        elif distance <= DISTANCE_2200:
            col_name = f'-2200({track})'
        elif distance <= DISTANCE_2600:
            col_name = f'-2600({track})'
        else:
            col_name = f'2600-({track})'

        cols = [col_name, f'{col_name}.1', f'{col_name}.2', f'{col_name}.3']

        total_row = df_stal.loc[df_stal['年度'] == '累計']
        if total_row.empty:
            raise ValueError("累計行が見つかりません")

        # 元コードでは [1] を使っていますが、
        # フィルタ後の行が1行想定なら iloc[0] の方が安全です
        r1 = total_row.iloc[0][cols[0]]
        r2 = total_row.iloc[0][cols[1]]
        r3 = total_row.iloc[0][cols[2]]
        rno = total_row.iloc[0][cols[3]]

        race_count = 100
        r_sum = int(r1) + int(r2) + int(r3) + int(rno)

        if r_sum >= race_count:
            stallion_point = (int(r1) * 1 + int(r2) * 2 + int(r3) * 3 + int(rno) * 7) / r_sum
        else:
            auno = race_count - r_sum
            stallion_point = (
                int(r1) * 1 +
                int(r2) * 2 +
                int(r3) * 3 +
                int(rno) * 7 +
                auno * 6.3
            ) / race_count

        if stallion_point == 0:
            stallion_point = DEFAULT_POINT

    except (
        ImportError,
        KeyError,
        ZeroDivisionError,
        ValueError,
        IndexError,
        AttributeError,
        requests.exceptions.RequestException,
    ) as e:
        logging.info(f'get_stallion error: horse_id={horse_id}, {type(e).__name__}: {e}')

    return pd.Series({
        'stal_id': stallion_id,
        'stal_name': stallion_name,
        'stal_point': stallion_point
    })


###########################################################################
# 生産者情報を取得
###########################################################################
def get_breeder(horse_id):
    breeder_id = ''
    breeder_name = ''
    breeder_point = 0.07

    try:
        # 馬ページから生産者情報を取得
        horse_url = f'https://db.netkeiba.com/horse/{horse_id}'
        soup = fetch_page_soup(horse_url)

        profile_table = soup.find("table", attrs={"summary": re.compile(r'のプロフィール')})
        if profile_table is None:
            raise ValueError("プロフィールテーブルが見つかりません")

        texts = profile_table.find_all(
            "a",
            attrs={"href": re.compile(r"^/breeder")}
        )

        if not texts:
            raise ValueError("生産者リンクが見つかりません")

        # 生産者ID・生産者名を取得
        breeder_href = texts[0]["href"]
        m = re.search(r'^/breeder/(\w+)', breeder_href)
        if not m:
            raise ValueError("生産者IDを抽出できません")

        breeder_id = m.group(1)
        breeder_name = texts[0].get_text(strip=True)

        # 生産者成績ページを取得
        breeder_url = f'https://db.netkeiba.com/breeder/result/{str(breeder_id).zfill(6)}'
        response = M_common.get_with_retry(requests, breeder_url, timeout=10.0)
        response.encoding = response.apparent_encoding

        df_result = pd.read_html(response.text, header=0)[0]

        #years = ['2022', '2023', '2024']
        # 固定年ではなく直近３年を取得
        current_year = datetime.datetime.now().year
        years = [str(current_year - 3), str(current_year - 2), str(current_year - 1)]
        win_rate_list = []

        for year in years:
            if year in df_result['年度'].astype(str).values:
                rate = df_result.loc[df_result['年度'].astype(str) == year, '勝率'].iloc[0]
                win_rate_list.append(float(rate))
            else:
                win_rate_list.append(breeder_point)

        breeder_point = sum(win_rate_list) / len(win_rate_list)

    except (
        ImportError,
        KeyError,
        ValueError,
        AttributeError,
        IndexError,
        requests.exceptions.RequestException,
    ) as e:
        logging.info(f'get_breeder error: horse_id={horse_id}, {type(e).__name__}: {e}')

    return pd.Series({
        'breeder_id': breeder_id,
        'breeder_name': breeder_name,
        'breeder_point': breeder_point
    })


###########################################################################
# 気象庁から各地方の気温を取得
###########################################################################
def get_temp(place, year, month, day, hmin):
    temp = np.nan

    # 開催地それぞれのキーワードを取得
    place_map = {
        '札幌': ('14', '47412', 's'),
        '函館': ('23', '47430', 's'),
        '福島': ('36', '47595', 's'),
        '中山': ('45', '1236', 'a'),
        '東京': ('44', '1133', 'a'),
        '新潟': ('54', '47604', 's'),
        '中京': ('51', '47636', 's'),
        '京都': ('61', '47759', 's'),
        '阪神': ('63', '47770', 's'),
    }

    # デフォルト（小倉など）
    prec, block, alfa = place_map.get(place, ('82', '0780', 'a'))

    url = (
        'https://www.data.jma.go.jp/obd/stats/etrn/view/10min_'
        f'{alfa}1.php?prec_no={prec}&block_no={block}'
        f'&year={year}&month={month}&day={day}&view=p1'
    )

    try:
        res = M_common.get_with_retry(requests, url, timeout=10.0)
        res.encoding = res.apparent_encoding

        df = pd.read_html(res.text, header=0)[0]

        # 分の一の位をゼロに統一（09:55 → 09:50）
        hmin_rounded = hmin[:4] + '0'

        row = df.loc[df['時分'] == hmin_rounded]

        if not row.empty:
            temp = row['気温(℃)'].iloc[0]

    except (
        ValueError,
        KeyError,
        IndexError,
        requests.exceptions.RequestException,
    ) as e:
        logging.info(f'get_temp error: place={place}, {year}-{month}-{day} {hmin}, {type(e).__name__}: {e}')

    return temp


###########################################################################
# 気候別成績を取得
###########################################################################
def get_climate(row):
    df_climate = pd.read_csv('data/horse_ped_climate.csv', dtype={'stal_id': 'str'})
    ave_temp = 8.0

    stallion_id = str(row.iloc[1])
    stallion_name = row.iloc[2]
    target_temp = float(row.iloc[0])

    try:
        exists = (df_climate['stal_id'].astype(str) == stallion_id).any()

        # 未登録なら新規取得
        if not exists:
            df_race = pd.read_csv(
                'data/race_data.csv',
                dtype={'クラス': 'str', '人気': 'str', '生産者ID': 'str'}
            )

            url = f'https://db.netkeiba.com/?pid=horse_select&id={stallion_id}&year=0000&mode=en&type=sire'
            soup = fetch_page_soup(url)
            pager = soup.find("div", attrs={"class": "pager"})
            if pager is None:
                raise AttributeError("pager が見つかりません")

            text = pager.text
            page = math.ceil(int(re.findall(r'(\d+)件中', text)[0]) / 20)

            column = [
                '日付', '開催', '天気', 'R', 'レース名', '映像', '頭数', '枠番', '馬番', '単勝',
                '人気', '着順', '馬名', '騎手', '斤量', '距離', '馬場', 'タイム', '着差', '通過',
                'ペース', '上り', '馬体重', '勝ち馬', '賞金(万円)'
            ]
            df_tmp = pd.DataFrame(index=[], columns=column)

            for cnt in range(page):
                url_detail = (
                    f'https://db.netkeiba.com/?pid=horse_select&id={stallion_id}'
                    f'&year=0000&mode=en&type=sire&course=&page={cnt + 1}'
                )
                res_detail = M_common.get_with_retry(session, url_detail, timeout=10.0)
                res_detail.encoding = "EUC-JP"

                df_page = pd.read_html(res_detail.text, header=0)[0]
                df_tmp = pd.concat([df_tmp, df_page], ignore_index=True)

            df_ped = df_tmp.reset_index(drop=True)

            # 降着・除外などを除外
            for i in range(len(df_ped)):
                pos = str(df_ped.loc[i, '着順'])
                if pos in ['失', '取', '除', '中'] or '降' in pos:
                    df_ped.loc[i, '着順'] = np.nan

            df_ped = df_ped.dropna(subset=['着順'])

            rank_12 = rank_12_18 = rank_18_25 = rank_25_30 = rank_30 = 0.0
            cnt_12 = cnt_12_18 = cnt_18_25 = cnt_25_30 = cnt_30 = 0

            for idx2, row2 in df_ped.iterrows():
                date = str(row2['日付']).replace('/', '')
                race_kai = row2['開催'][0].zfill(2)
                course_name = row2['開催'][1:3]
                course_id = M_common.get_courseID(course_name)
                race_week = row2['開催'][3:4].zfill(2)
                race_id = date[0:4] + course_id + race_kai + race_week + str(row2['R']).zfill(2)

                race_temp_row = df_race.loc[df_race['レースID'] == int(race_id), '気温']
                if race_temp_row.empty:
                    continue

                temp = race_temp_row.iloc[0]
                df_ped.loc[idx2, '気温'] = temp

                rank = int(row2['着順'])

                if temp <= TEMP_12:
                    rank_12 += rank
                    cnt_12 += 1
                elif temp <= TEMP_18:
                    rank_12_18 += rank
                    cnt_12_18 += 1
                elif temp <= TEMP_25:
                    rank_18_25 += rank
                    cnt_18_25 += 1
                elif temp <= TEMP_30:
                    rank_25_30 += rank
                    cnt_25_30 += 1
                else:
                    rank_30 += rank
                    cnt_30 += 1

            cnt_list = [cnt_12, cnt_12_18, cnt_18_25, cnt_25_30, cnt_30]
            rank_list = [rank_12, rank_12_18, rank_18_25, rank_25_30, rank_30]

            for i in range(5):
                if cnt_list[i] == 0:
                    rank_list[i] = DEFAULT_POINT
                else:
                    rank_list[i] = rank_list[i] / cnt_list[i]

            columns = [
                'stal_id', 'stal_name',
                '着順平均(~12)', '着順平均(12~18)', '着順平均(18~25)',
                '着順平均(25~30)', '着順平均(30~)'
            ]
            df_new = pd.DataFrame({
                'stal_id': [stallion_id],
                'stal_name': [stallion_name],
                '着順平均(~12)': [rank_list[0]],
                '着順平均(12~18)': [rank_list[1]],
                '着順平均(18~25)': [rank_list[2]],
                '着順平均(25~30)': [rank_list[3]],
                '着順平均(30~)': [rank_list[4]]
            })

            df_new.to_csv(
                './data/horse_ped_climate.csv',
                mode='a',
                header=False,
                index=False,
                sep=',',
                columns=columns
            )

            # 追加後に再読込しないと、この後の検索に反映されない
            df_climate = pd.read_csv('data/horse_ped_climate.csv', dtype={'stal_id': 'str'})

        matched = df_climate.loc[df_climate['stal_id'].astype(str) == stallion_id]
        if matched.empty:
            return ave_temp

        if target_temp <= TEMP_12:
            ave_temp = matched['着順平均(~12)'].iloc[0]
        elif target_temp <= TEMP_18:
            ave_temp = matched['着順平均(12~18)'].iloc[0]
        elif target_temp <= TEMP_25:
            ave_temp = matched['着順平均(18~25)'].iloc[0]
        elif target_temp <= TEMP_30:
            ave_temp = matched['着順平均(25~30)'].iloc[0]
        else:
            ave_temp = matched['着順平均(30~)'].iloc[0]

    except (
        ValueError,
        IndexError,
        AttributeError,
        KeyError,
        requests.exceptions.RequestException,
    ) as e:
        logging.info(f'get_climate error: stal_id={stallion_id}, {type(e).__name__}: {e}')

    return ave_temp


###########################################################################
# 脚質を取得
###########################################################################
def get_running_style(race_id):
    url = f'https://race.netkeiba.com/race/result.html?race_id={race_id}'

    try:
        response = M_common.get_with_retry(requests, url, timeout=10.0)
        response.encoding = response.apparent_encoding

        df = pd.read_html(response.text, header=0)[0]
        df['脚質'] = ''
        df['出走頭数'] = len(df)

        for idx, row in df.iterrows():
            corner_lst = str(row['コーナー通過順']).split('-')

            if not corner_lst or corner_lst == ['nan']:
                df.loc[idx, '脚質'] = ''
                continue

            last_corner = corner_lst[-1]

            # 最終コーナー順位が数値でない場合を考慮
            try:
                last_corner_num = float(last_corner)
            except ValueError:
                df.loc[idx, '脚質'] = ''
                continue

            # 最終コーナー以外で1位なら逃げ(1)
            found_style = False
            for i in range(len(corner_lst) - 1):
                if corner_lst[i] == '1':
                    df.loc[idx, '脚質'] = '1'
                    found_style = True
                    break

            if found_style:
                continue

            # 最終コーナーで4位以内なら先行(2)
            if last_corner_num <= 4:
                df.loc[idx, '脚質'] = '2'

            # 出走頭数が8以上
            elif row['出走頭数'] >= 8:
                # 最終コーナーで出走頭数の2/3以内なら差し(3)
                if last_corner_num <= row['出走頭数'] * (2 / 3):
                    df.loc[idx, '脚質'] = '3'
                else:
                    df.loc[idx, '脚質'] = '4'

            # 少頭数ならそれ以外は追い込み(4)
            else:
                df.loc[idx, '脚質'] = '4'

        return df['コーナー通過順'], df['脚質']

    except (
        ValueError,
        KeyError,
        IndexError,
        requests.exceptions.RequestException,
    ) as e:
        logging.info(f'get_running_style error: race_id={race_id}, {type(e).__name__}: {e}')
        return pd.Series(dtype='object'), pd.Series(dtype='object')


###########################################################################
# レースデータを取得
###########################################################################
def get_race_data(id_list, race_type):
    # レース情報を取得
    first_loop = True
    for race_id in tqdm(id_list):
        try:
            url = M_common.get_url(race_type) + race_id

            # アクセス拒否対応 2024.11.10
            # リトライ対応 2026.3.26
            response = M_common.get_with_retry(requests, url, timeout=10.0)
            response.encoding = response.apparent_encoding
            df = pd.read_html(response.text, header=0)[0]
            #html = M_common.get_with_retry(session, url, headers=headers, timeout=10.0)
            #html.encoding = "EUC-JP"
            #soup = BeautifulSoup(html.text, "html.parser")
            soup = BeautifulSoup(response.text, "html.parser")

            # レース情報を取得
            texts = get_sourceTexts(soup, race_type)
            info = re.findall(r'\w+', texts)

            date = ''
            race_distance = 0
            track = ''
            for text in info:
                if ("年" in text) and (race_type == 'previous'):
                    date = M_common.conv_date(text)
                if "m" in text:
                    race_distance = int(re.findall('(\d+)m', text)[0])
                if "芝" in text:
                    track = '芝'
                if "ダ" in text:
                    track = 'ダート'
                if text in ["良", "稍", "稍重", "重", "不良", "不"]:
                    df['状態'] = text
                if "歳" in text:
                    df['クラス'] = text
            df['タイプ'] = track
            df['距離'] = race_distance

            if race_type == 'previous':
                # レース名を取得
                race_name = soup.find("div", attrs={"class": "data_intro"}).find_all("h1")[0].text
                # タイムの':'を'.'に置換
                df['タイム'] = df['タイム'].replace('(.*):(.*)', r'\1.\2', regex=True)
                # 欠損値処理
                df['着順'] = df['着順'].astype('str').apply(
                    lambda x: '' if re.findall(r'失 | 取 | 除 | 中 | 降', x) else x)

                # 発走時刻を取得
                stime_tmp = re.findall('発走 : (\d+):(\d+)', texts)[0]
            else:
                # レース名を取得
                race_name = info[0]
                # データフレームを整形する
                df = df.drop(index=0)
                df = df.reset_index()
                df = df.rename(columns={'馬体重(増減)': '馬体重', '枠': '枠番'})
                # 発走時刻を取得
                stime_tmp = re.findall('(\d+):(\d+)発走', texts)[0]

                # 日付
                #date = TODAY
                date_list = []
                date_text = soup.find("dd", attrs={"class": "Active"}).find_all(
                    "a", attrs={"href": re.compile(".*kaisai_date=(\d)")}
                )
                for a in date_text:
                    race_id = re.findall(r"\d+", a["href"])
                    date_list.append(race_id[0])
                date = date_list[0]

            df['出走頭数'] = len(df)
            horse_num = len(df)

            # フィードバックモードの場合は馬体重を更新する
            if race_type == 'previous' or WEIGHT_FLAG == 1:
                df['増減'] = df['馬体重'].apply(lambda x: '' if x == '計不' or x == '前計不' or x == '--' else re.findall('(?<=\().*(?=\))', x)[0])
                df['馬体重'] = df['馬体重'].apply(lambda x: '' if x == '計不' or x == '前計不' or x == '--' else x[0:3])
                # 脱退した馬の馬体重を欠損値とする
                df.loc[df['馬体重'] == '--', '馬体重'] = ''
            else:
                df['馬体重'] = ''

            # レースIDとレース名を先頭に挿入
            df['日付'] = date
            df['レースID'] = race_id
            df['レース名'] = race_name
            df['競馬場'] = M_common.get_courseName(race_id)

            # 発走時刻を取得
            stime = stime_tmp[0] + ':' + stime_tmp[1]
            df['発走時刻'] = stime

            # 気温を取得
            date_y = int(date[:4])
            date_m = int(date[4:6])
            date_d = int(date[6:8])
            if race_type == 'previous' or WEIGHT_FLAG == 1:
                df['気温'] = get_temp(M_common.get_courseName(race_id), date_y, date_m, date_d, stime)
            else:
                df['気温'] = M_common.get_temp_new(M_common.get_courseName(race_id), stime)

            # 馬ID・騎手ID・調教師IDを取得
            df['馬ID'] = get_id(soup, 'horse', race_type)
            df['騎手ID'] = get_id(soup, 'jockey', race_type)
            df['調教師ID'] = get_id(soup, 'trainer', race_type)

            # 調教タイムと評価を取得
            if race_type == 'previous':
                df[['調教タイム', '調教評価', '調教コース', '調教指数']] = df['馬ID'].apply(get_training_time, race_id=race_id)
            elif race_type == 'new':
                training_df = pd.DataFrame(
                    get_training_time_new(race_id),
                    columns=['調教タイム', '調教評価', '調教コース', '調教指数']
                )
                df[['調教タイム', '調教評価', '調教コース', '調教指数']] = training_df

            # 過去実績を取得
            pastrace_data = get_past_race(race_id, horse_num)
            list_pastrace = pd.DataFrame(
                 data=pastrace_data,
                 columns=[
                     '馬ID', '同コース同距離1着', '同コース同距離2着', '同コース同距離3着', '同コース同距離着外',
                     '同距離1着', '同距離2着', '同距離3着', '同距離着外', '短距離1着', '短距離2着','短距離3着',
                     '短距離着外', '長距離1着', '長距離2着', '長距離3着', '長距離着外', '同コース同距離実績指数',
                     '同距離指数', '短距離指数', '長距離指数'
                 ]
            )
            df = pd.merge(df, list_pastrace, how="left", on="馬ID")

            # タイム指数を取得
            if '新馬' in race_name:
                df['タイム指数MAX'] = DEFAULT_TIMEINDEX
                df['タイム指数平均'] = DEFAULT_TIMEINDEX
                df['タイム指数距離MAX'] = DEFAULT_TIMEINDEX
                df['タイム指数コースMAX'] = DEFAULT_TIMEINDEX
            else:
                time_index = get_timeindex(race_id, horse_num)
                list_timeindex = pd.DataFrame(
                    data=time_index,
                    columns=['馬ID', 'タイム指数MAX', 'タイム指数平均', 'タイム指数距離MAX', 'タイム指数コースMAX'
                             ]
                )
                df = pd.merge(df, list_timeindex, how="left", on="馬ID")

            # 調子偏差値を取得
            condition_deviation = get_conditiondeviation(race_id, horse_num)
            list_conditiondeviation = pd.DataFrame(data=condition_deviation,
                                                  columns=['馬ID', '調子偏差値'])
            df = pd.merge(df, list_conditiondeviation, how="left", on="馬ID")

            # 血統データを取得
            df[['種牡馬ID', '種牡馬名', '種牡馬指数']] = \
                df['馬ID'].apply(get_stallion, distance=race_distance, track=track, race_type=1)
            df[['母父ID', '母父名', '母父指数']] = \
                df['馬ID'].apply(get_stallion, distance=race_distance, track=track, race_type=2)

            # 種牡馬指数と父母指数の平均値を算出
            df['血統指数'] = df[['種牡馬指数', '母父指数']].apply(lambda x: (x['種牡馬指数'] + x['母父指数'])/2, axis=1)

            # 生産者データを取得
            df[['生産者ID', '生産者名', '生産者指数']] = df['馬ID'].apply(get_breeder)

            # 気候別成績を取得
            df['気候適性'] = df[['気温', '種牡馬ID', '種牡馬名']].apply(get_climate, axis=1)

            # 脚質を取得
            if race_type == 'previous':
                df['コーナー通過順'], df['脚質'] = get_running_style(race_id)

            # 列名の並び替え
            df = df.reindex(columns=_config["data"]["columns"])

            # データフレームをCSVに書き込む
            first_loop = write_csv(first_loop, df, f'./data/race_data_{race_type}.csv')
        # エラー処理
        except (
                ValueError,
                KeyError,
                IndexError,
                requests.exceptions.RequestException,
        ) as e:
            logging.info(f'get_raceData error: race_id={race_id}, {type(e).__name__}: {e}')
            continue


###########################################################################
# メイン処理
###########################################################################
def main():
    print('0:   過去のレースデータ（全レース）を作成')
    print('1:   過去のレースデータ（直近のみ）を作成')
    print('2:   最新のレースデータを作成（馬体重が未確定の場合）')
    print('3:   最新のレースデータを作成（全レース馬体重が確定済の場合）')
    print('4:　　デバッグモード')
    print('------------------------------------------------------')
    select = input('対象のデータを選択： ')

    # 計測スタート
    t_start = datetime.datetime.now()
    YEAR = t_start.year

    # 過去のレースデータ作成
    if select == '0':
        # レースIDリストを作成
        # place = list(range(1, 11, 1))
        # kai = day = r = list(range(1, 13, 1))
        id_list = M_common.get_target_race_id_list(YEAR, YEAR)

        # 過去のレースデータを作成
        get_race_data(id_list, 'previous')
    # 過去（直近）のレースデータ作成
    elif select == '1':
        # レースIDリストを作成
        id_list = M_common.get_target_race_id_list(YEAR, YEAR)

        # 過去のレースデータを作成
        get_race_data(id_list, 'previous')
    # 最新のレースデータ作成
    elif select == '2' or select == '3':
        if select == '2':       WEIGHT_FLAG = 0  # 馬体重は空白
        elif select == '3':     WEIGHT_FLAG = 1  # 馬体重を取得
        # レースIDリストを作成
        id_list = M_common.get_target_race_id_list(YEAR, YEAR)

        # 日付
        t_now = datetime.datetime.now()
        # TODAY = str(t_now.year).zfill(4) + str(t_now.month).zfill(2) + str(t_now.day).zfill(2)
        # TODAY = '20230203'

        # 最新のレースデータを作成
        get_race_data(id_list, 'new')
    # デバッグモード
    elif select == '4':
        id_list = ['202405050812']
        print(id_list)
        get_race_data(id_list, 'previous')
    else:
        pass

    t_proc = datetime.datetime.now() - t_start

    print('処理時間：', t_proc)
    print('終了...!!')


if __name__ == '__main__':
    initialize_netkeiba()
    main()
