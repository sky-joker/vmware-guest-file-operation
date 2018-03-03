# vmware-guest-file-operation

VMwareのGuestOSに対してファイルのダウンロード及びファイルのアップロードをするツール

## 必要条件

* python3
* pyvmomi
* clint
* requests

## インストール

```bash
$ git clone https://github.com/sky-joker/vmware-guest-file-operation.git
$ cd vmware-guest-file-operation
$ pip3 install -r requirements.txt
$ chmod +x vmware-guest-file-operation.py
```

## 使い方

ツールを使う時に必要となる認証情報は以下のものです。

* vCenterアカウント/パスワード
* GuestOSアカウント/パスワード

### GuestOSからファイルをダウンロード

仮想マシン名 `devel2` `devel3` `devel3-rhel` から `hoge.txt` をダウンロードします。

```
$ ./vmware-guest-file-operation.py -vc vcenter.local -tvm devel2 devel3 devel3-rhel -gu root download -dpth /root/hoge.txt -spth ./hoge.txt
vCenter Password:
Guest OS Password:
vCenter Login process...                [success]
download file from devel3               [################################] 1/1 - 00:00:00
download file from devel2               [################################] 1/1 - 00:00:00
download file from devel3-rhel          [################################] 1/1 - 00:00:00
```

### GuestOSへファイルをアップロード

仮想マシン `devel2` `devel3` `devel3-rhel` へ `hoge.txt` をアップロードします。

```
$ ./vmware-guest-file-operation.py -vc vcenter.local -tvm devel2 devel3 devel3-rhel -gu root upload -upth ./hoge.txt -spth /root/hoge.txt
vCenter Password:
Guest OS Password:
vCenter Login process...                [success]
devel3 file upload process...           [success]
devel2 file upload process...           [success]
devel3-rhel file upload process...      [success]
```

### GuestOSへファイルをアップロードした後にコマンドを実行する

仮想マシン `devel2` `devel3` `devel3-rhel` へ `hoge.txt` をアップロードした後に `rm -f` で削除します。

```
./vmware-guest-file-operation.py -vc vcenter.local -tvm devel2 devel3 devel3-rhel -gu root upload -upth ./hoge.txt -spth /root/hoge.txt -c /usr/bin/rm -cargs "-f hoge.txt"
vCenter Password:
Guest OS Password:
vCenter Login process...                [success]
devel3 file upload process...           [success]
devel2 file upload process...           [success]
devel3-rhel file upload process...      [success]
devel3 command execute finish           [success]
devel2 command execute finish           [success]
devel3-rhel command execute finish      [success]
```

## ToDo

- [X] マルチスレッド化
- [ ] 実行処理のYAML化
- [X] ダウンロード処理で一つのファイルに書き込まれてしまう課題

## ライセンス

[MIT](https://github.com/sky-joker/vmware-guest-file-operation/blob/master/LICENSE.txt)

## 作者

[sky-joker](https://github.com/sky-joker)
