# 競馬予想

## 概要
競馬出走データをスクレイピングし、このデータを元に勝ち馬を予想するプログラム

## 使い方
以下の手順に従ってプログラムを実行する。

- 事前準備
0. M_common.pyを開き、対象の競馬場や回数（レース開催日）を設定する。

- 過去の出走データの作成
1. M_get_RaceData.pyの実行
  netkeiba.comから過去数年間の競馬出走データ「./data/race_data.csv」を作成する。
2. M_get_train.pyの実行
  上記で作成したデータを元に、学習用データ「./data/training.csv」を作成する。
3. M_get_models.pyの実行
  上記の学習用データ「training.csv」を元に、学習モデルファイル「./models/◯◯.pkl」を作成する。

- 勝ち馬予想データの作成
4. M_get_RaceData.pyの実行
  netkeiba.comから予想したい最新の競馬出走データ「./data/race_data_new.csv」を作成する。
5. M_get_train.pyの実行
  上記で作成したデータを元に、予想用データ「./data/testing.csv」を作成する。
6. M_pred_win.pyの実行
  学習モデルファイルを読み込み、予想用データ「./data/testing.csv」を元に勝ち馬予想データ「./predictions/◯◯.csv」を作成する。

## 使用技術
Python, pandas など
