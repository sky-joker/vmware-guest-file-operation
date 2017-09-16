# vmware-guest-file-operation

VMwareのGuestOSに対してファイルのダウンロード及びファイルのアップロードをするツール

## 必要条件

* python3
* pyvmomi
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

仮想マシン名 `centos` から `hoge.txt` をダウンロードします。

```bash
$ ./vmware-guest-file-operation.py -vc vcenter01.local -tvm centos -gu root download -dpth /root/hoge.txt -spth ./hoge.txt
vCenter Password:
Guest OS Password:
file download success.
```

### GuestOSへファイルをアップロード

仮想マシン `centos` へ `hoge.txt` をアップロードします。

```bash
$ ./vmware-guest-file-operation.py -vc vcenter01.local -tvm centos -gu root upload -upth ./hoge.txt -spth /root/hoge.txt
vCenter Password:
Guest OS Password:
file upload success.
```

## ライセンス

[MIT](https://github.com/sky-joker/vmware-guest-file-operation/blob/master/LICENSE.txt)

## 作者

[sky-joker](https://github.com/sky-joker)
