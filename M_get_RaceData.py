#
# 処理内容：レースデータを作成 ver 2.0
# 作成日：2022/9/8
#
import M_common
import re
import pandas as pd
from tqdm import tqdm
import requests
from urllib3.util import Retry
from urllib.error import URLError
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from itertools import product
import numpy as np
import datetime
import math
import time  # 遅延のためにtime.sleepを利用
from selenium import webdriver
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
# selenium 4
# from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
# 'webdriver_manager’をインストールする$ pip3 install webdriver_manager
from webdriver_manager.chrome import ChromeDriverManager

# パスを通すためのコード
# chromdriverを手動でインストールするコマンドはこちらから（https://pypi.org/project/chromedriver-binary/#history）
# ※chromのバージョンとdriverを揃える
# バージョンを指定したインストールpip install chromedriver-binary==125.0.6422.141
# == で指定するバージョンは各自がインストールしているChromeブラウザのバージョンにより異なるので、
# Chrome > Help > About Google Chrome から確認してください。
import chromedriver_binary

WEIGHT_FLAG = 0         # 馬体重の取得有無（0:なし 1:あり）
DEFAULT_TIME = 67.0     # 調教タイム（デフォルト値）
DEFALUT_POINT = 7.0     # 血統指数（デフォルト値）
DEFALUT_TIMEINDEX = 70  # スピード指数（デフォルト値）
TODAY = 0

# ログイン
USER = M_common.USER
PASS = M_common.PASS
login_info = M_common.login_info
# セッション開始
session = requests.session()
retries = Retry(total=5,  # リトライ回数
                backoff_factor=1,  # sleep時間
                status_forcelist=[500, 502, 503, 504])  # timeout以外でリトライするステータスコード
session.mount("https://", HTTPAdapter(max_retries=retries))
url_login = 'https://regist.netkeiba.com/account/?pid=login&action=auth'
res_login = session.post(url_login, data=login_info)

# アクセス拒否対応 2024.11.10 S
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
}
# アクセス拒否対応 2024.11.10 E

options = webdriver.ChromeOptions()
# バックグラウンド処理
options.add_argument('--headless')
sample_driver = Chrome(options=options)
# seleniumもログインする
sample_driver.get(url_login)    # ログイン画面に接続
login_id = sample_driver.find_element(By.NAME, "login_id")
Login_pass = sample_driver.find_element(By.NAME, "pswd")
login_id.clear()
Login_pass.clear()
login_id.send_keys(USER)
Login_pass.send_keys(PASS)
sample_driver.find_element(By.XPATH, "/html/body/div[1]/div/div/form/div/div[1]/input").click()


###########################################################################
# 馬・騎手・調教師IDリストの作成
###########################################################################
def get_id(soup, str, type):
    id_list = []
    a_list = []
    if type == 'previous':
        a_list = soup.find("table", attrs={"summary": "レース結果"}).find_all(
            "a", attrs={"href": re.compile("^/" + str)}
        )
    elif type == 'new':
        a_list = soup.find("div", attrs={"class": "RaceTableArea"}).find_all(
            "a", attrs={"href": re.compile(".*/" + str + "/")}
        )
    for a in a_list:
        id = re.findall(r"\d+", a["href"])
        id_list.append(id[0])
    return id_list

###########################################################################
# 調教評価のポイント変換
###########################################################################
def get_TrainingPoint(ev_str):
    sign = ['A', 'B', 'C', 'D', 'E']
    p = [0.75, 0.775, 0.8, 0.9, 1.0]
    #p = [0.6, 0.7, 0.8, 0.9, 1.0]
    point = 1.0
    for i in range(5):
        if ev_str == sign[i]:   point = p[i]
    return point

###########################################################################
# ソースコード内のテキスト取得
###########################################################################
def get_sourceTexts(soup, type):
    texts = ''
    if type == 'previous':
        texts = (
                soup.find("div", attrs={"class": "data_intro"}).find_all("p")[0].text
                + soup.find("div", attrs={"class": "data_intro"}).find_all("p")[1].text
        )
    elif type == 'new':
        texts = soup.find("h1", attrs={"class": "RaceName"}).text
        for i in range(2):
            texts = texts + soup.find(
                #"div", attrs={"class": "RaceList_NameBox"}).find_all("span")[i].text
                "div", attrs={"class": "RaceList_NameBox"}).find_all("div")[i].text
    return texts

###########################################################################
# 過去レースの調教タイム取得
###########################################################################
def get_TrainingTime(id, race_id):
    time = DEFAULT_TIME     # 調教タイム
    val = 'E'               # 調教評価
    crs = ''                # 調教コース
    time_p = DEFAULT_TIME   # 調教指数
    retry_i = 0             # 繰り返し回数
    while retry_i < 5:
        try:
            retry_i = retry_i + 1
            url_tt = 'https://db.netkeiba.com/?pid=horse_training&id=' + str(id) + '&rid=' + str(race_id)

            # アクセス拒否対応 2024.11.10 S
            #res_tt = session.get(url_tt, timeout=10.0)
            res_tt = session.get(url_tt, timeout=10.0, headers=headers)
            # アクセス拒否対応 2024.11.10 E

            soup_tt = BeautifulSoup(res_tt.content, "html.parser")
            df_tt = pd.read_html(res_tt.content)[0]

            # 調教評価・調教コースをセット
            val = df_tt['評価.1'][0]
            crs = df_tt['コース'][0]
            crs_bln = df_tt['コース'].isnull()[0]

            # 調教情報取得
            text_tt = soup_tt.find("table", attrs={"summary": "調教タイム"}).find_all("li")
            # 調教タイムリスト
            tt_list = []
            for t in text_tt:
                tt = re.findall(r'>(.*)<', str(t))
                tt_list.append(tt)

            # 4Fと1Fの調教タイムの合計値を取得
            # 坂以外は左から３番目と５番目の調教タイムを取得
            if crs_bln == True:
                return pd.Series({'time': time, 'val': val, 'crs': crs, 'time_p': time_p})

            if "坂" in crs:
                time = round((float((tt_list[1][0])) + float(tt_list[4][0])) * M_common.get_TrainingBasis(crs),2)
            else:
                time = round((float((tt_list[2][0])) + float(tt_list[4][0])) * M_common.get_TrainingBasis(crs),2)

            # 調教指数を算出
            point = get_TrainingPoint(val)
            time_p = round(time * point, 3)

        # 調教タイムが取得できなかった場合
        except (AttributeError, ValueError, IndexError, ImportError):
            pass
        except TimeoutError:
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('TimeoutError：', url_tt)
                pass
        except URLError:
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('URLError：', url_tt)
                pass

        return pd.Series({'time': time, 'val': val, 'crs': crs, 'time_p': time_p})

###########################################################################
# 最新レースの調教タイム取得
###########################################################################
def get_TrainingTimeNew(race_id):
    retry_i = 0  # 繰り返し回数
    while retry_i < 5:
        try:
            url_tt = 'https://race.netkeiba.com/race/oikiri.html?race_id=' + str(race_id) + '&rf=race_submenu'

            # アクセス拒否対応 2024.11.10 S
            #res_tt = session.get(url_tt, timeout=10.0)
            res_tt = session.get(url_tt, timeout=10.0, headers=headers)
            # アクセス拒否対応 2024.11.10 E

            soup_tt = BeautifulSoup(res_tt.content, "html.parser")
            df_tt = pd.read_html(res_tt.content)[0]

            text_tt = soup_tt.find("table", attrs={"id": "All_Oikiri_Table"}).find_all(
                "ul", attrs={"class": "TrainingTimeDataList"}
            )
            # 調教コース取得
            df_bln = df_tt['コース'].isnull()      # NaNの有無を格納
            course_list = df_tt['コース']

            # 調教タイム・評価リスト・調教コース・調教指数
            list = []
            for i in range(len(df_tt)):
                # NaNが含まれている場合
                if df_bln[i] == True:
                    list.append([DEFAULT_TIME, 'E', '', DEFAULT_TIME])
                # 計不が含まれている場合
                elif '計' in df_tt['調教タイム ラップ表示'][i]:
                    list.append([DEFAULT_TIME, 'E', '', DEFAULT_TIME])
                else:
                    # 4Fと1Fの調教タイムの合計値を取得
                    # 坂以外は左から３番目と５番目の調教タイムを取得
                    tt = re.findall(r'(\d+\.\d+)|-', str(text_tt[i]))
                    if "坂" in course_list[i] and "門" not in course_list[i]:
                        time = round((float(tt[1]) + float(tt[7])) * M_common.get_TrainingBasis(course_list[i]), 2)
                    elif len(tt) == 10:
                        time = round((float(tt[4]) + float(tt[8])) * M_common.get_TrainingBasis(course_list[i]), 2)
                    elif len(tt) == 9:
                        time = round((float(tt[3]) + float(tt[7])) * M_common.get_TrainingBasis(course_list[i]), 2)
                    elif len(tt) == 8:
                        time = round((float(tt[2]) + float(tt[6])) * M_common.get_TrainingBasis(course_list[i]), 2)
                    else:
                        time = DEFAULT_TIME

                    time_p = round(time * get_TrainingPoint(df_tt['評価.1'][i]), 3)

                    # 調教タイム、調教評価、調教コース、調教指数をセット
                    list.append([time, df_tt['評価.1'][i], df_tt['コース'][i], time_p])

        except TimeoutError:
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('TimeoutError：', url_tt)
                pass
        except URLError:
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('URLError：', url_tt)
                pass

        return list

###########################################################################
# 過去レースの実績取得
###########################################################################
def get_PastRace(race_id, horse_num):
    retry_i = 0
    while retry_i < 5:
        try:
            retry_i = retry_i + 1
            url_tt = 'https://race.netkeiba.com/race/newspaper.html?m=riot-racedetail-past5-data&race_id=' + str(race_id)
            sample_driver.get(url_tt)

            # time.sleep(1) # 読み込むまで待つはなし https://qiita.com/uguisuheiankyo/items/cec03891a86dfda12c9a
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'DataCellWrap01')))

            # 辞書・リストの初期化
            list = []

            horse_num = horse_num + 2
            # 過去実績のXpathを取得するラムダ関数
            els_path = '/html/body/div[1]/div[5]/div[2]/div/div[3]/riot-racedetail-past5-data/div/div[2]/table/tbody/tr['
            els_lambda = lambda x, y, z: sample_driver.find_elements(
                By.XPATH, els_path + str(x) + ']/td[8]/table/tbody/tr[' + str(y) + ']/td[' + str(z) + ']')

            # 各馬の過去実績を取得
            for i in range(2, horse_num):
                # 馬ID
                horse_IDels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[5]/dl/dt[2]/a')

                # 同コース同距離1着・同コース同距離2着・同コース同距離3着・同コース同距離着外
                horse_CRCD1els, horse_CRCD2els, horse_CRCD3els, horse_CRCD4els\
                    = els_lambda(i,1,2), els_lambda(i,1,3), els_lambda(i,1,4), els_lambda(i,1,5)

                # 同距離1着・同距離2着・同距離3着・同距離着外
                horse_CD1els, horse_CD2els,  horse_CD3els, horse_CD4els\
                    = els_lambda(i,3,2), els_lambda(i,3,3), els_lambda(i,3,4), els_lambda(i,3,5)

                # 200m短い距離1着・短い距離2着・短い距離3着・短い距離着外
                horse_SD1els, horse_SD2els, horse_SD3els, horse_SD4els \
                    = els_lambda(i,2,2), els_lambda(i,2,3), els_lambda(i,2,4), els_lambda(i,2,5)

                # 200m長い距離1着・長い距離2着・長い距離3着・長い距離着外
                horse_LD1els, horse_LD2els, horse_LD3els, horse_LD4els\
                    = els_lambda(i,4,2), els_lambda(i,4,3), els_lambda(i,4,4), els_lambda(i,4,5)

                pastrace_p = DEFALUT_POINT  # 過去同コース同距離指数
                pastCDrace_p = DEFALUT_POINT  # 過去同距離指数
                pastSDrace_p = DEFALUT_POINT  # 過去短い距離指数
                pastLDrace_p = DEFALUT_POINT  # 過去長い距離指数

                # 馬IDを取得（おそらくIDがない馬はいなさそう）
                if len(horse_IDels) == 0:   #取得できていない場合はもう一度読み込み
                    continue

                for horse_IDel in horse_IDels:
                    horse_IDs = horse_IDel.get_attribute("href")
                    # 馬IDを取得
                    p = r'https://db.netkeiba.com/horse/(.*)/'  # 「https://db.netkeiba.com/horse/」の後ろにあるIDだけを抽出したい
                    m = re.search(p, horse_IDs)
                    horse_IDs = m.group(1)

                # 要素が取れなかった場合の処理
                if len(horse_CRCD1els) == 0 or len(horse_CRCD2els) == 0 or len(horse_CRCD3els) == 0 or len(horse_CRCD4els) == 0 or len(horse_CD1els) == 0 or len(horse_CD2els) == 0 or len(horse_CD3els) == 0 or len(horse_CD4els) == 0:
                    horse_CRCD1 = horse_CRCD2 = horse_CRCD3 = horse_CRCD4 = 0
                    horse_CD1 = horse_CD2 = horse_CD3 = horse_CD4 = 0
                    horse_SD1 = horse_SD2 = horse_SD3 = horse_SD4 = 0
                    horse_LD1 = horse_LD2 = horse_LD3 = horse_LD4 = 0
                else:
                    for horse_CRCD1el, horse_CRCD2el, horse_CRCD3el, horse_CRCD4el, horse_CD1el, horse_CD2el, horse_CD3el, horse_CD4el, \
                        horse_SD1el, horse_SD2el, horse_SD3el, horse_SD4el, horse_LD1el, horse_LD2el, horse_LD3el, horse_LD4el \
                            in zip(horse_CRCD1els, horse_CRCD2els, horse_CRCD3els, horse_CRCD4els, horse_CD1els, horse_CD2els, horse_CD3els, horse_CD4els,
                                horse_SD1els, horse_SD2els, horse_SD3els, horse_SD4els, horse_LD1els, horse_LD2els, horse_LD3els, horse_LD4els):
                        horse_CRCD1 = int(horse_CRCD1el.text)
                        horse_CRCD2 = int(horse_CRCD2el.text)
                        horse_CRCD3 = int(horse_CRCD3el.text)
                        horse_CRCD4 = int(horse_CRCD4el.text)
                        horse_CD1 = int(horse_CD1el.text)
                        horse_CD2 = int(horse_CD2el.text)
                        horse_CD3 = int(horse_CD3el.text)
                        horse_CD4 = int(horse_CD4el.text)
                        horse_SD1 = int(horse_SD1el.text)
                        horse_SD2 = int(horse_SD2el.text)
                        horse_SD3 = int(horse_SD3el.text)
                        horse_SD4 = int(horse_SD4el.text)
                        horse_LD1 = int(horse_LD1el.text)
                        horse_LD2 = int(horse_LD2el.text)
                        horse_LD3 = int(horse_LD3el.text)
                        horse_LD4 = int(horse_LD4el.text)

                        # 加重平均？
                        ave_lambda = lambda x1,x2,x3,x4: np.average([1, 2, 3, 7], weights=[x1, x2, x3, x4]) \
                            if  x1 != 0 or x2 != 0 or x3 != 0 or x4 != 0 else DEFALUT_POINT
                        pastrace_p = ave_lambda(horse_CRCD1, horse_CRCD2, horse_CRCD3, horse_CRCD4)
                        pastCDrace_p = ave_lambda(horse_CD1, horse_CD2, horse_CD3, horse_CD4)
                        pastSDrace_p = ave_lambda(horse_SD1, horse_SD2, horse_SD3, horse_SD4)
                        pastLDrace_p = ave_lambda(horse_LD1, horse_LD2, horse_LD3, horse_LD4)

                list.append([horse_IDs, horse_CRCD1, horse_CRCD2, horse_CRCD3, horse_CRCD4, horse_CD1, horse_CD2, horse_CD3, horse_CD4,
                            horse_SD1, horse_SD2, horse_SD3, horse_SD4, horse_LD1, horse_LD2, horse_LD3, horse_LD4,
                            pastrace_p, pastCDrace_p, pastSDrace_p, pastLDrace_p])

            return list

        except ZeroDivisionError:
            print('Error')
            break
        except (TimeoutException, StaleElementReferenceException):
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('TimeoutError：', url_tt)
                continue

###########################################################################
# タイム指数を取得
###########################################################################
def get_timeindex(race_id, horse_num):
    retry_i = 0
    while retry_i < 5:
        try:
            retry_i = retry_i + 1

            url_tt = 'https://race.netkeiba.com/race/speed.html?race_id=' + str(race_id) + '&type=rank&mode=max#d'
            sample_driver.get(url_tt)
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'Average')))
            AVE_MAXels = sample_driver.find_elements(By.XPATH,
                                                           '/html/body/div[1]/div[3]/div[4]/p[2]/strong')
            # 平均を取得する
            # 最大の平均
            for AVE_MAXel in AVE_MAXels:
                if AVE_MAXel.text == '-':
                    AVE_MAX = 0
                else:
                    AVE_MAX = AVE_MAXel.text

            # 平均の平均
            url_tt = 'https://race.netkeiba.com/race/speed.html?race_id=' + str(race_id) + '&type=rank&mode=average#d'
            sample_driver.get(url_tt)
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'Average')))
            AVE_AVEels = sample_driver.find_elements(By.XPATH,
                                                     '/html/body/div[1]/div[3]/div[4]/p[2]/strong')
            for AVE_AVEel in AVE_AVEels:
                if AVE_AVEel.text == '-':
                    AVE_AVE = 0
                else:
                    AVE_AVE = AVE_AVEel.text

            # 距離の平均
            url_tt = 'https://race.netkeiba.com/race/speed.html?race_id=' + str(race_id) + '&type=rank&mode=distance#d'
            sample_driver.get(url_tt)
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'Average')))
            AVE_DISels = sample_driver.find_elements(By.XPATH,
                                                     '/html/body/div[1]/div[3]/div[4]/p[2]/strong')
            for AVE_DISel in AVE_DISels:
                if AVE_DISel.text == '-':
                    AVE_DIS = 0
                else:
                    AVE_DIS = AVE_DISel.text

            # コースの平均
            url_tt = 'https://race.netkeiba.com/race/speed.html?race_id=' + str(race_id) + '&type=rank&mode=course#d'
            sample_driver.get(url_tt)
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'Average')))
            AVE_COUels = sample_driver.find_elements(By.XPATH,
                                                     '/html/body/div[1]/div[3]/div[4]/p[2]/strong')
            for AVE_COUel in AVE_COUels:
                if AVE_COUel.text == '-':
                    AVE_COU = 0
                else:
                    AVE_COU = AVE_COUel.text

            # 個々のデータを取得する
            url_tt = 'https://race.netkeiba.com/race/speed.html?race_id=' + str(race_id) + '&rf=shutuba_submenu'
            sample_driver.get(url_tt)

            # time.sleep(1) # 読み込むまで待つはなし https://qiita.com/uguisuheiankyo/items/cec03891a86dfda12c9a
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'list')))

            # 辞書・リストの初期化
            list = []

            horse_num = horse_num + 1
            els_path = '/html/body/div[1]/div[3]/div[4]/table/tbody/tr['

            # タイム指数MAX・・タイム指数平均・タイム指数距離MAX・タイム指数コースMAX
            for i in range(1, horse_num):
                horse_IDels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[4]/a')
                timeindex_maxels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[8]/a')
                timeindex_aveels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[9]')
                timeindex_disels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[10]/a')
                timeindex_couels = sample_driver.find_elements(By.XPATH, els_path + str(i) + ']/td[11]/a')

                # 馬IDを取得（おそらくIDがない馬はいなさそう）
                if len(horse_IDels) == 0:   #取得できていいない場合はもう一度読み込み
                    continue

                for horse_IDel in horse_IDels:
                    horse_IDs = horse_IDel.get_attribute("href")
                    # 馬IDを取得
                    p = r'https://db.netkeiba.com/horse/(.*)'  # 「https://db.netkeiba.com/horse/」の後ろにあるIDだけを抽出したい.何故か後ろに/が無い
                    m = re.search(p, horse_IDs)
                    horse_IDs = m.group(1)
                    horse_IDs = horse_IDs.replace('/', '')  # 後ろに/が入るパターンがある

                # 要素が取れなかった場合の処理
                if len(timeindex_maxels) == 0:
                    timeindex_max = AVE_MAX
                else:
                    for timeindex_maxel in timeindex_maxels:
                        if timeindex_maxel.text == '-':
                            timeindex_max = AVE_MAX
                        else:
                            timeindex_max = int(timeindex_maxel.text.replace('*', ''))

                # 要素が取れなかった場合の処理
                if len(timeindex_aveels) == 0:
                    timeindex_ave = AVE_AVE
                else:
                    for timeindex_aveel in timeindex_aveels:
                        if timeindex_aveel.text == '-':
                            timeindex_ave = AVE_AVE
                        else:
                            timeindex_ave = int(timeindex_aveel.text.replace('*', ''))

                # 要素が取れなかった場合の処理
                if len(timeindex_disels) == 0:
                    timeindex_dis = AVE_DIS
                else:
                    for timeindex_disel in timeindex_disels:
                        if timeindex_disel.text == '-':
                            timeindex_dis = AVE_DIS
                        else:
                            timeindex_dis = int(timeindex_disel.text.replace('*', ''))

                # 要素が取れなかった場合の処理
                if len(timeindex_couels) == 0:
                    timeindex_cou = AVE_COU
                else:
                    for timeindex_couel in timeindex_couels:
                        if timeindex_couel.text == '-':
                            timeindex_cou = AVE_COU
                        else:
                            timeindex_cou = int(timeindex_couel.text.replace('*', ''))

                list.append([horse_IDs, timeindex_max, timeindex_ave, timeindex_dis, timeindex_cou])

            return list

        except ZeroDivisionError:
            print('Error')
            break
        except (TimeoutException, StaleElementReferenceException):
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('TimeoutError：', url_tt)
                continue


###########################################################################
# 調子偏差値を取得
###########################################################################
def get_conditiondeviation(race_id, horse_num):
    retry_i = 0
    while retry_i < 5:
        try:
            retry_i = retry_i + 1
            url_tt = 'https://race.sp.netkeiba.com/barometer/score.html?race_id=' + str(race_id) + '&rf=rs'
            sample_driver.get(url_tt)

            # time.sleep(1) # 読み込むまで待つはなし https://qiita.com/uguisuheiankyo/items/cec03891a86dfda12c9a
            # CLASS名指定したページ上の要素が読み込まれるまで待機（15秒でタイムアウト判定）
            WebDriverWait(sample_driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, 'Shutuba_HorseList.BaroTableArea')))

            # 辞書・リストの初期化
            list = []

            horse_numbers = horse_num + 1

            # タイム指数MAX・・タイム指数平均・タイム指数距離MAX・タイム指数コースMAX
            for i in range(1, horse_numbers):
                horse_IDels = sample_driver.find_elements(By.XPATH,
                                                          '/html/body/div[1]/div/div[8]/table/tbody/tr[' + str(
                                                              i) + ']/td[3]/dl/dt/a')
                condition_deviationels = sample_driver.find_elements(By.XPATH,
                                                               '/html/body/div[1]/div/div[8]/table/tbody/tr[' + str(
                                                                   i) + ']/td[4]/span[1]')

                # デバッグ用
                # print('i：', i, len(horse_IDels), len(condition_deviationels))

                # 馬IDを取得（おそらくIDがない馬はいなさそう）
                if len(horse_IDels) == 0:  # 取得できていいない場合はもう一度読み込み
                    continue

                for horse_IDel in horse_IDels:
                    horse_IDs = horse_IDel.get_attribute("href")
                    # 馬IDを取得
                    p = r'horse_id=(.*)&race_id'  # 「horse_id=」の後ろにあって「&race_id」の間にあるIDだけを抽出したい.
                    m = re.search(p, horse_IDs)
                    horse_IDs = m.group(1)

                # 調子偏差値処理
                for condition_deviationel in condition_deviationels:
                    condition_deviation = int(condition_deviationel.text)

                list.append([horse_IDs, condition_deviation])

                # print(list)   # デバック用

            return list

        except ZeroDivisionError:
            print('Error')
            break
        except (TimeoutException, StaleElementReferenceException):
            if retry_i < 5:
                time.sleep(1)
                continue
            else:
                print('TimeoutError：', url_tt)
                continue


###########################################################################
# 種牡馬データを取得
###########################################################################
def get_stallion(horse_id, distance, track, type):
    if type == 1:
        file_name = 'data/horse_ped.csv'
    else:
        file_name = 'data/horse_ped2.csv'
    df = pd.read_csv(file_name)
    stal_list = df['horse_id'].astype(str).values

    stal_id = ''
    stal_name = ''
    stal_point = DEFALUT_POINT
    find_flag = False
    try:
        # リストの馬から種牡馬を取得
        for i in range(len(stal_list)):
            if str(horse_id) == stal_list[i]:
                stal_id = df['stal_id'][i]
                stal_name = df['stal_name'][i]
                find_flag = True
        # リストにない場合、競馬サイトから種牡馬名を取得
        if find_flag == False:
            url = 'https://db.netkeiba.com/horse/' + str(horse_id)
            # アクセス拒否対応 2024.11.10 S
            #html = session.get(url, timeout=10.0)
            html = session.get(url, timeout=10.0, headers=headers)
            # アクセス拒否対応 2024.11.10 E
            html.encoding = "EUC-JP"
            soup = BeautifulSoup(html.text, "html.parser")
            texts = soup.find("table", attrs={"summary": re.compile(r'血統表')}).find_all(
                    "a", attrs={"href": re.compile("^/" + 'horse')}
                )
            # 血統のIDリストを取得
            id_list = []
            for a in texts:
                id = re.findall(r'^/horse/ped/(\w+)', a["href"])
                id_list.append(id[0])
            if type == 1:
                stal_id = id_list[0]
            else:
                stal_id = id_list[4]
            # 血統の馬名リストを取得
            familly_list = []
            for a in texts:
                name = re.findall(r'>(.*)<', str(a))
                familly_list.append(name[0])
            if type == 1:   stal_name = familly_list[0]
            else:           stal_name = familly_list[4]

            # 各種牡馬の賞金累計を格納したデータフレームを作成
            columns = ['horse_id', 'stal_id', 'stal_name', 'money']
            df_ped = pd.DataFrame({'horse_id': [horse_id], 'stal_id': [stal_id], 'stal_name': [stal_name], 'money': ''})
            # データフレームをCSVに書き込む
            if type == 1:
                df_ped.to_csv('./data/horse_ped.csv', mode='a', header=False, index=False, sep=',', columns=columns)
            else:
                df_ped.to_csv('./data/horse_ped2.csv', mode='a', header=False, index=False, sep=',', columns=columns)

        # 種牡馬の産駒成績を取得
        url_stal = 'https://db.netkeiba.com/?pid=horse_sire&id=' + str(stal_id) + '&course=1&mode=1&type=2'
        # アクセス拒否対応 2024.11.10 S
        res_stal = requests.get(url_stal, headers=headers)
        res_stal.encoding = res_stal.apparent_encoding
        # アクセス拒否対応 2024.11.10 E
        if track == '芝':
            # アクセス拒否対応 2024.11.10 S
            #df_stal = pd.read_html(url_stal, header=0)[0]
            df_stal = pd.read_html(res_stal.text, header=0)[0]
            # アクセス拒否対応 2024.11.10 E
        else:
            # アクセス拒否対応 2024.11.10 S
            #df_stal = pd.read_html(url_stal, header=0)[1]
            df_stal = pd.read_html(res_stal.text, header=0)[1]
            # アクセス拒否対応 2024.11.10 E
        col_name = ''
        if distance <= 1400:
            col_name = '-1400(' + track + ')'
        elif distance > 1400 and distance <= 1800:
            col_name = '-1800(' + track + ')'
        elif distance > 1800 and distance <= 2200:
            col_name = '-2200(' + track + ')'
        elif distance > 2200 and distance <= 2600:
            col_name = '-2600(' + track + ')'
        elif distance > 2600:
            col_name = '2600-(' + track + ')'

        col = [col_name, col_name + '.1', col_name + '.2', col_name + '.3']
        # 距離別の成績を取得
        r1 = df_stal.loc[df_stal['年度'] == '累計', col[0]][1]
        r2 = df_stal.loc[df_stal['年度'] == '累計', col[1]][1]
        r3 = df_stal.loc[df_stal['年度'] == '累計', col[2]][1]
        rno = df_stal.loc[df_stal['年度'] == '累計',col[3]][1]

        # 種牡馬指数の算出
        # 100レース未満の場合、6.3で埋める
        RACE_COUNT = 100
        r_sum = int(r1) + int(r2) + int(r3) + int(rno)
        if r_sum >= RACE_COUNT:
            stal_point = (int(r1) * 1 + int(r2) * 2 + int(r3) * 3 + int(rno) * 7) / r_sum
        else:
            auno = RACE_COUNT - r_sum
            stal_point = (int(r1) * 1 + int(r2) * 2 + int(r3) * 3 + int(rno) * 7 + auno * 6.3) / RACE_COUNT

        if stal_point == 0:
            stal_point = DEFALUT_POINT

    # 戦歴がない場合はスルー
    except (ImportError, KeyError, ZeroDivisionError, ValueError):
        pass
    except TimeoutError:
        print('TimeoutError：', url)
        pass

    return pd.Series({'stal_id':stal_id, 'stal_name':stal_name, 'stal_point':stal_point})

###########################################################################
# 生産者情報を取得
###########################################################################
def get_breeder(horse_id):
    breeder_id = ''
    breeder_name = ''
    breeder_point = 0.07
    try:
        url = 'https://db.netkeiba.com/horse/' + str(horse_id)
        # アクセス拒否対応 2024.11.10 S
        #html = session.get(url, timeout=10.0)
        html = session.get(url, timeout=10.0, headers=headers)
        # アクセス拒否対応 2024.11.10 S
        html.encoding = "EUC-JP"
        soup = BeautifulSoup(html.text, "html.parser")
        # 生産者を探索
        texts = soup.find("table", attrs={"summary": re.compile(r'のプロフィール')}).find_all(
            "a", attrs={"href": re.compile("^/" + 'breeder')}
        )
        # 生産者IDを取得
        for a in texts:
            id = re.findall(r'^/breeder/(\w+)', a["href"])
            breeder_id = id[0]
        # 生産者名を取得
        for a in texts:
            name = re.findall(r'>(.*)<', str(a))
            breeder_name = name[0]

        # 生産者の成績を取得
        url = 'https://db.netkeiba.com/breeder/result/' + str(breeder_id).zfill(6)
        # アクセス拒否対応 2024.11.10 S
        response = requests.get(url, headers=headers)
        response.encoding = response.apparent_encoding
        #df_result = pd.read_html(url, header=0)[0]
        df_result = pd.read_html(response.text, header=0)[0]
        # アクセス拒否対応 2024.11.10 E
        years = ['2022', '2023', '2024']
        winRate_list = []
        for i in range(len(years)):
            if years[i] in df_result['年度'].values:
                winRate_list.append(float(df_result.loc[df_result['年度'] == years[i], '勝率'].values))
            else:
                winRate_list.append(0.07)

        # 三年分の勝率の平均値
        breeder_point = (winRate_list[0] + winRate_list[1] + winRate_list[2]) / 3

    except (ImportError, KeyError, ValueError, AttributeError):
        pass
    except TimeoutError:
        print('TimeoutError：', url)
        pass

    return pd.Series({'breeder_id':breeder_id, 'breeder_name':breeder_name, 'breeder_point':breeder_point})

###########################################################################
# 気象庁から各地方の気温を取得
###########################################################################
def get_temp(place, year, month, day, hmin):
    temp = np.nan
    try:
        if place == '札幌':
            prec, block, alfa = '14', '47412', 's'
        elif place == '函館':
            prec, block, alfa = '23', '47430', 's'
        elif place == '福島':
            prec, block, alfa  = '36', '47595', 's'
        elif place == '中山':
            prec, block, alfa  = '45', '1236', 'a'
        elif place == '東京':
            prec, block, alfa  = '44', '1133', 'a'
        elif place == '新潟':
            prec, block, alfa  = '54', '47604', 's'
        elif place == '中京':
            prec, block, alfa  = '51', '47636', 's'
        elif place == '京都':
            prec, block, alfa  = '61', '47759', 's'
        elif place == '阪神':
            prec, block, alfa  = '63', '47770', 's'
        else:
            prec, block, alfa  = '82', '0780', 'a'

        url = 'https://www.data.jma.go.jp/obd/stats/etrn/view/10min_' + alfa + '1.php?prec_no=' \
            + prec + '&block_no=' + block + '&year=' \
            + str(year) + '&month=' + str(month) + '&day=' + str(day) + '&view=p1'
        df = pd.read_html(url, header=0)[0]

        # 分の一の位をゼロに統一する（09:55-->09:50）
        hmin = hmin[:4] + '0'
        temp = df.loc[df['時分'] == hmin, '気温(℃)'].values[0]
    except ImportError:
        pass

    return temp

###########################################################################
# 気候別成績を取得
###########################################################################
def get_climate(row):
    df_climate = pd.read_csv('data/horse_ped_climate.csv')
    stal_list = df_climate['stal_id'].astype(str).values
    ave_temp = 8.0
    find_flag = False

    try:
        # リストの馬から種牡馬を取得
        for i in range(len(stal_list)):
            if str(row.iloc[1]) == stal_list[i]:
                find_flag = True

        # リストにない場合は、新たに種牡馬の気候適性を取得
        if find_flag == False:
            df_race = pd.read_csv('data/race_data.csv',
                                  dtype={'クラス':'str', '人気': 'str', '生産者ID': 'str'})
            url = 'https://db.netkeiba.com/?pid=horse_select&id=' + str(row.iloc[1]) \
                  + '&year=0000&mode=en&type=sire'
            # アクセス拒否対応 2024.11.10 S
            #html = session.get(url, timeout=10.0)
            html = session.get(url, timeout=10.0, headers=headers)
            # アクセス拒否対応 2024.11.10 E
            html.encoding = "EUC-JP"
            soup = BeautifulSoup(html.text, "html.parser")
            text = soup.find("div", attrs={"class": "pager"}).text

            # ページ件数
            page = math.ceil(int(re.findall('(\d+)件中', text)[0]) / 20)
            column = ['日付', '開催', '天気', 'R', 'レース名', '映像', '頭数', '枠番', '馬番', '単勝',
                      '人気', '着順', '馬名', '騎手', '斤量', '距離', '馬場', 'タイム', '着差', '通過',
                      'ペース', '上り', '馬体重', '勝ち馬', '賞金(万円)']
            df_tmp = df_ped = pd.DataFrame(index=[], columns=column)
            for cnt in range(page):
                url_detail = 'https://db.netkeiba.com/?pid=horse_select&id=' + str(row.iloc[1]) \
                      + '&year=0000&mode=en&type=sire&course=&page=' + str(cnt+1)
                df_ped = pd.read_html(url_detail, header=0)[0]
                df_ped = pd.concat([df_tmp, df_ped])
                df_tmp = df_ped
            df_ped = df_ped.reset_index(drop=True)

            # 降着したものを除外
            for i in range(len(df_ped)):
                pos = str(df_ped['着順'][i])
                # 脱落した馬は除外
                if pos == '失' or pos == '取' or pos == '除' or pos == '中' or '降' in pos:
                    df_ped.loc[i, '着順'] = np.nan
            df_ped = df_ped.dropna(subset=['着順'])

            # 産駒成績の明細行分ループ
            rank_12 = rank_12_18 = rank_18_25 = rank_25_30 = rank_30 = 0.0
            cnt_12 = cnt_12_18 = cnt_18_25 = cnt_25_30 = cnt_30 = 0
            for idx2, row2 in df_ped.iterrows():
                date = str(row2.日付).replace('/','')
                race_kai = row2.開催[0].zfill(2)
                course_name = row2.開催[1:3]
                course_id = M_common.get_courseID(course_name)
                race_week = row2.開催[3:4].zfill(2)
                race_id = date[0:4] + course_id + race_kai + race_week + str(row2.R).zfill(2)

                temp = df_race.loc[(df_race['レースID'] == int(race_id)), '気温'].values[0]
                df_ped.loc[idx2, '気温'] = temp

                if temp <= 12.0:
                    rank_12 = rank_12 + int(row2.着順)
                    cnt_12 = cnt_12 + 1
                elif temp > 12.0 and temp <= 18.0:
                    rank_12_18 = rank_12_18 + int(row2.着順)
                    cnt_12_18 = cnt_12_18 + 1
                elif temp > 18.0 and temp <= 25.0:
                    rank_18_25 = rank_18_25 + int(row2.着順)
                    cnt_18_25 = cnt_18_25 + 1
                elif temp > 25.0 and temp <= 30.0:
                    rank_25_30 = rank_25_30 + int(row2.着順)
                    cnt_25_30 = cnt_25_30 + 1
                else:
                    rank_30 = rank_30 + int(row2.着順)
                    cnt_30 = cnt_30 + 1

            cnt_list = [cnt_12, cnt_12_18, cnt_18_25, cnt_25_30, cnt_30]
            rank_list = [rank_12, rank_12_18, rank_18_25, rank_25_30, rank_30]
            # 各気候の着順平均を算出
            for i in range(5):
                if cnt_list[i] == 0:
                    rank_list[i] = DEFALUT_POINT
                else:
                    rank_list[i] = rank_list[i] / cnt_list[i]

            # 各種牡馬の賞金累計を格納したデータフレームを作成
            columns = ['stal_id', 'stal_name', '着順平均(~12)','着順平均(12~18)','着順平均(18~25)','着順平均(25~30)','着順平均(30~)']
            df_ped = pd.DataFrame({
                'stal_id': [row.iloc[1]],'stal_name': [row.iloc[2]],'着順平均(~12)': [rank_list[0]],
                '着順平均(12~18)': [rank_list[1]],'着順平均(18~25)': [rank_list[2]],
                '着順平均(25~30)': [rank_list[3]],'着順平均(30~)': [rank_list[4]]
            })
            # データフレームをCSVに書き込む
            df_ped.to_csv('./data/horse_ped_climate.csv', mode='a', header=False, index=False, sep=',', columns=columns)

        if float(row.iloc[0]) <= 12.0:
            ave_temp = df_climate.loc[df_climate['stal_id'] == row.iloc[1], '着順平均(~12)'].values[0]
        elif float(row.iloc[0]) > 12.0 and float(row.iloc[0]) <= 18.0:
            ave_temp = df_climate.loc[df_climate['stal_id'] == row.iloc[1], '着順平均(12~18)'].values[0]
        elif float(row.iloc[0]) > 18.0 and float(row.iloc[0]) <= 25.0:
            ave_temp = df_climate.loc[df_climate['stal_id'] == row.iloc[1], '着順平均(18~25)'].values[0]
        elif float(row.iloc[0]) > 25.0 and float(row.iloc[0]) <= 30.0:
            ave_temp = df_climate.loc[df_climate['stal_id'] == row.iloc[1], '着順平均(25~30)'].values[0]
        else:
            ave_temp = df_climate.loc[df_climate['stal_id'] == row.iloc[1], '着順平均(30~)'].values[0]

    # ページが存在しない
    except (ValueError, IndexError):
        pass
    # 種牡馬成績が存在しない
    except AttributeError:
        pass
    except TimeoutError:
        print('TimeoutError：', url)
        pass

    return ave_temp

###########################################################################
# 脚質を取得
###########################################################################
def get_runningStyle(race_id):
    try:
        url = 'https://race.netkeiba.com/race/result.html?race_id=' + race_id

        # アクセス拒否対応 2024.11.10 S
        response = requests.get(url, headers=headers)
        response.encoding = response.apparent_encoding
        #df = pd.read_html(url, header=0)[0]
        df = pd.read_html(response.text, header=0)[0]
        #html = session.get(url, timeout=10.0)
        html = session.get(url, timeout=10.0, headers=headers)
        # アクセス拒否対応 2024.11.10 E

        html.encoding = "EUC-JP"
        df['脚質'] = ''
        df['出走頭数'] = len(df)

        for idx, row in df.iterrows():
            corner_lst = str(row.コーナー通過順).split('-')
            for i in range(len(corner_lst)):
                # 最終コーナー以外で１位だった場合、逃げ(1)
                if (i != len(corner_lst) - 1) and (corner_lst[i] == '1'):
                    df.loc[idx, '脚質'] = '1'
                    break
                # 最終コーナーで４位以内だった場合、先行(2)
                elif corner_lst[len(corner_lst) - 1] <= '4':
                    df.loc[idx, '脚質'] = '2'
                # 出走頭数が8以上
                elif row.出走頭数 >= 8:
                    # 最終コーナーで出走頭数の2/3以内だった場合、差し(3)
                    if float(corner_lst[len(corner_lst) - 1]) <= (row.出走頭数) * (2 / 3):
                        df.loc[idx, '脚質'] = '3'
                    # 上記以外は、追い込み(4)
                    else:
                        df.loc[idx, '脚質'] = '4'
                else:
                    df.loc[idx, '脚質'] = '4'

        return df['コーナー通過順'], df['脚質']

    # ページが見つからない場合はスルー
    except IndexError:
        pass
    except ImportError:
        pass
    except TimeoutError:
        print('TimeoutError：', url)
        pass

###########################################################################
# レースデータを取得
###########################################################################
def get_raceData(id_list, type):
    # レース情報を取得
    first_loop = True
    for race_id in tqdm(id_list):
        try:
            url = M_common.get_url(type) + race_id

            # アクセス拒否対応 2024.11.10 S
            response = requests.get(url, headers=headers)
            response.encoding = response.apparent_encoding
            #df = pd.read_html(url, header=0)[0]
            df = pd.read_html(response.text, header=0)[0]
            #html = session.get(url, timeout=10.0)
            html = session.get(url, timeout=10.0, headers=headers)
            # アクセス拒否対応 2024.11.10 E

            html.encoding = "EUC-JP"
            soup = BeautifulSoup(html.text, "html.parser")

            # レース情報を取得
            texts = get_sourceTexts(soup, type)
            info = re.findall(r'\w+', texts)

            date = ''
            race_distance = 0
            track = ''
            for text in info:
                if ("年" in text) and (type == 'previous'):
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

            if type == 'previous':
                # レース名を取得
                race_name = soup.find("div", attrs={"class": "data_intro"}).find_all("h1")[0].text
                # タイムの':'を'.'に置換
                df['タイム'] = df['タイム'].replace('(.*):(.*)', r'\1.\2', regex=True)
                # 欠損値処理
                df['着順'] = df['着順'].astype('str').apply(lambda x: '' if re.findall(r'失|取|除|中|降', x) else x)

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
                    id = re.findall(r"\d+", a["href"])
                    date_list.append(id[0])
                date = date_list[0]

            df['出走頭数'] = len(df)
            horse_num = len(df)

            # フィードバックモードの場合は馬体重を更新する
            if type == 'previous' or WEIGHT_FLAG == 1:
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
            if type == 'previous' or WEIGHT_FLAG == 1:
                df['気温'] = get_temp(M_common.get_courseName(race_id), date_y, date_m, date_d, stime)
            else:
                df['気温'] = M_common.get_temp_new(M_common.get_courseName(race_id), stime)

            # 馬ID・騎手ID・調教師IDを取得
            df['馬ID'] = get_id(soup, 'horse', type)
            df['騎手ID'] = get_id(soup, 'jockey', type)
            df['調教師ID'] = get_id(soup, 'trainer', type)

            # 調教タイムと評価を取得
            if type == 'previous':
                df[['調教タイム','調教評価','調教コース','調教指数']] = df['馬ID'].apply(get_TrainingTime, race_id=race_id)
            elif type == 'new':
                df[['調教タイム','調教評価','調教コース','調教指数']] = get_TrainingTimeNew(race_id)

            # 過去実績を取得
            pastrace_data = get_PastRace(race_id, horse_num)
            list_pastrace = pd.DataFrame(data=pastrace_data, columns=['馬ID','同コース同距離1着','同コース同距離2着','同コース同距離3着','同コース同距離着外',
                                                                      '同距離1着','同距離2着','同距離3着','同距離着外','短距離1着','短距離2着','短距離3着','短距離着外',
                                                                      '長距離1着','長距離2着','長距離3着','長距離着外','同コース同距離実績指数','同距離指数','短距離指数','長距離指数'])
            df = pd.merge(df, list_pastrace, how="left", on="馬ID")

            # タイム指数を取得
            if '新馬' in race_name:
                df['タイム指数MAX'] = DEFALUT_TIMEINDEX
                df['タイム指数平均'] = DEFALUT_TIMEINDEX
                df['タイム指数距離MAX'] = DEFALUT_TIMEINDEX
                df['タイム指数コースMAX'] = DEFALUT_TIMEINDEX
            else:
                time_index = get_timeindex(race_id, horse_num)
                list_timeindex = pd.DataFrame(data=time_index,
                                              columns=['馬ID', 'タイム指数MAX', 'タイム指数平均', 'タイム指数距離MAX', 'タイム指数コースMAX'])
                df = pd.merge(df, list_timeindex, how="left", on="馬ID")

            # 調子偏差値を取得
            condition_deviation = get_conditiondeviation(race_id, horse_num)
            list_conditiondeviation = pd.DataFrame(data=condition_deviation,
                                                  columns=['馬ID', '調子偏差値'])
            df = pd.merge(df, list_conditiondeviation, how="left", on="馬ID")

            # 血統データを取得
            df[['種牡馬ID','種牡馬名','種牡馬指数']] = \
                df['馬ID'].apply(get_stallion, distance=race_distance, track=track, type=1)
            df[['母父ID','母父名','母父指数']] = \
                df['馬ID'].apply(get_stallion, distance=race_distance, track=track, type=2)

            # 種牡馬指数と父母指数の平均値を算出
            df['血統指数'] = df[['種牡馬指数','母父指数']].apply(lambda x: (x['種牡馬指数'] + x['母父指数'])/2, axis=1)

            # 生産者データを取得
            df[['生産者ID','生産者名','生産者指数']] = df['馬ID'].apply(get_breeder)

            # 気候別成績を取得
            df['気候適性'] = df[['気温','種牡馬ID','種牡馬名']].apply(get_climate, axis=1)

            # 脚質を取得
            if type == 'previous':
                df['コーナー通過順'], df['脚質'] = get_runningStyle(race_id)

            # 列名の並び替え
            df = df.reindex(columns=M_common.columns)

            # データフレームをCSVに書き込む
            if first_loop:
                df.to_csv('./data/race_data_' + type + '.csv', index=False)
                first_loop = False
            else:
                df.to_csv('./data/race_data_' + type + '.csv', mode='a', header=False, index=False)
        # ページが見つからない場合はスルー
        except IndexError:
            pass
        except TimeoutError:
            print('TimeoutError：', url)
            pass

###########################################################################
# メイン処理
###########################################################################
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
    place = list(range(1, 11, 1))
    kai = day = r = list(range(1, 13, 1))
    id_list = M_common.get_RaceList(2024, 2024, place, kai, day, r)
    # id_list = M_common.get_RaceList(2023, 2023, [4, 5, 6, 7, 8, 9, 10, 11], kai, day, r)
    # id_list = M_common.get_RaceList(2021, 2021, place, [1], day, r)
    # id_list = M_common.get_RaceList(2022, 2022, place, [4, 5, 6, 7, 8, 9, 10, 11, 12], day, r)
    # id_list = M_common.get_RaceList(2022, 2022, [7], [6, 7, 8, 9, 10, 11, 12], day, r)
    #id_list = M_common.get_RaceList(2022, 2022, [8, 9, 10, 11], [4, 5, 6, 7, 8, 9, 10, 11, 12], day, r)
    # id_list = M_common.get_RaceList(2022, 2022, [6], [5, 6, 7, 8, 9, 10, 11, 12], [6, 7, 8, 9, 10, 11, 12], r)

    # 過去のレースデータを作成
    get_raceData(id_list, 'previous')
# 過去（直近）のレースデータ作成
elif select == '1':
    # レースIDリストを作成
    id_list = []
    for place in M_common.PLACES:
        kai, day = M_common.get_DAY(place)
        id_list = id_list + M_common.get_RaceList(YEAR, YEAR, place, kai, day, list(range(1, 13, 1)))

    # 過去のレースデータを作成
    get_raceData(id_list, 'previous')
# 最新のレースデータ作成
elif select == '2' or select == '3':
    if select == '2':       WEIGHT_FLAG = 0  # 馬体重は空白
    elif select == '3':     WEIGHT_FLAG = 1  # 馬体重を取得
    # レースIDリストを作成
    id_list = []
    for place in M_common.PLACES:
        kai, day = M_common.get_DAY(place)
        id_list = id_list + M_common.get_RaceList(YEAR, YEAR, place, kai, day, list(range(1, 13, 1)))

    # 日付
    t_now = datetime.datetime.now()
    TODAY = str(t_now.year).zfill(4) + str(t_now.month).zfill(2) + str(t_now.day).zfill(2)
    #TODAY = '20230203'

    # 最新のレースデータを作成
    get_raceData(id_list, 'new')
# デバッグモード
elif select == '4':
    #id_list = M_common.get_RaceList(2023, 2023, [10], [1], [1], [5])
    id_list = ['202405050812']
    print(id_list)
    t_now = datetime.datetime.now()
    TODAY = str(t_now.year).zfill(4) + str(t_now.month).zfill(2) + str(t_now.day).zfill(2)
    WEIGHT_FLAG = 0
    #get_raceData(id_list, 'new')
    get_raceData(id_list, 'previous')
else:
    pass

t_proc = datetime.datetime.now() - t_start

print('処理時間：', t_proc)
print('終了...!!')