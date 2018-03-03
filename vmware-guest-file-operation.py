#!/usr/bin/env python3
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
from getpass import getpass
from clint.textui import progress
import os
import time
import re
import ssl
import atexit
import argparse
import sys
import threading
import requests
# requestsの自己証明書の警告を出力しないようにする
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
__license__ = 'MIT'

class colors:
    GREEN = '\033[32m'
    RED = '\033[91m'
    END = '\033[0m'

class threadJob(threading.Thread):
    def __ini__(self):
        threading.Thread.__init__(self)
        self.vm_mob = ""
        self.args = ""
        self.upload_file = ""
        self.save_file = ""
        self.content = ""

def options():
    """
    コマンドラインオプション設定

    :rtype: class
    :return: argparse.Namespace
    """
    parser = argparse.ArgumentParser(prog='guest-file-operation.py',
                                     add_help=True,
                                     description='GuestOSのファイル操作をする')
    parser.add_argument('--host', '-vc',
                        type=str, required=True,
                        help='vCenterのIP又はホスト名')
    parser.add_argument('--username', '-u',
                        type=str, default='administrator@vsphere.local',
                        help='vCenterのログインユーザー名(default:administrator@vsphere.local)')
    parser.add_argument('--password', '-p',
                        type=str,
                        help='vCenterのログインユーザーパスワード')
    parser.add_argument('--targetvm', '-tvm',
                        type=str, required=True, nargs='+',
                        help='対象の仮想マシンを指定')
    parser.add_argument('--guestuser', '-gu',
                        type=str, required=True,
                        help='Guest OSのユーザーを指定')
    parser.add_argument('--guestpassword', '-gp',
                        type=str,
                        help='Guest OSのユーザーパスワードを指定')

    # サブコマンド設定
    subparsers = parser.add_subparsers()

    # ファイルダウンロードサブコマンド
    parser_download = subparsers.add_parser('download', help='仮想マシンからファイルをダウンロードする')
    parser_download.add_argument('--downloadpath', '-dpth',
                                 type=str, required=True,
                                 help='GuestOSからダウンロードする対象ファイルのフルパス')
    parser_download.add_argument('--savepath', '-spth',
                                 type=str, required=True,
                                 help='GuestOSからダウンロードしたファイルの保存先パス')
    parser_download.add_argument('--overwrite', '-ow',
                                 action='store_true',
                                 help='ダウンロードしたファイルの上書きを許可')
    parser_download.add_argument('--max-thread', '-mt',
                                 type=int, default='5',
                                 help='同時処理スレッドの最大数')
    parser_download.set_defaults(handler=download)

    # ファイルアップロードサブコマンド
    parser_upload = subparsers.add_parser('upload', help='仮想マシンにファイルをアップロードする')
    parser_upload.add_argument('--uploadpath', '-upth',
                               type=str, required=True,
                               help='GuestOSへアップロードするファイルのパス')
    parser_upload.add_argument('--savepath', '-spth',
                               type=str, required=True,
                                help='GuestOSへアップロードしたファイルの保存先フルパス')
    parser_upload.add_argument('--overwrite', '-ow',
                               action='store_true',
                               help='GuestOSに同名のファイル名があった場合の上書きを許可')
    parser_upload.add_argument('--cmd', '-c',
                               type=str,
                               help='ファイルアップロード後に実行するコマンド')
    parser_upload.add_argument('--cmd-args', '-cargs',
                               type=str,
                               help='ファイルアップロード後に実行するコマンドの引数')
    parser_upload.add_argument('--max-thread', '-mt',
                               type=int, default='5',
                               help='同時処理スレッドの最大数')
    parser_upload.set_defaults(handler=upload)

    args = parser.parse_args()

    if hasattr(args, 'handler'):
        if(not(args.password)):
            args.password = getpass(prompt='vCenter Password:')
        if(not(args.guestpassword)):
            args.guestpassword = getpass(prompt='Guest OS Password:')
        args.handler(args)
    else:
        parser.print_help()

def get_mob_info(content, mob, target=''):
    """
    Management Objectを取得する。
    targetが指定されていない場合はContainerView(https://goo.gl/WXMfJK)で返す。

    :type content: vim.ServiceInstanceContent
    :param content: ServiceContent(https://goo.gl/oMtVFh)

    :type mob: Management Object
    :param mob: 取得する対象のManagement Objectを指定

    :type target: str
    :param target: 返すmobの名前を指定

    :rtype: Management Object
    :return: 指定したManagement Object又はContainerViewを返す

    :rtype: list
    :return: 指定したManagement Objectのリストを返す
    """
    try:
        r = content.viewManager.CreateContainerView(content.rootFolder,
                                                    [mob],
                                                    True)
    except Exception as error:
        sys.stderr.write('get the Managed Object...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
        sys.stderr.write('err msg: ' + colors.RED + error.msg + colors.END + '\n')
        sys.exit(1)

    # 返すmobを名前で指定する場合
    vm_mobs = []
    for t in target:
        for vm_mob in r.view:
            if(vm_mob.name == t):
                vm_mobs.append(vm_mob)
                break

    # targetの存在確認
    for vm_mob in vm_mobs:
        for t in target:
            if(vm_mob.name == t):
                target.remove(t)

    if(len(target) > 0):
        for t in target:
            sys.stderr.write('error msg: ' + colors.RED + t + ' not found.' + colors.END + '\n')

    # vm_mobsの個数を確認
    if(len(vm_mobs) == 0):
        sys.stderr.write('error msg: ' + colors.RED + 'target vms not found' + colors.END)
        sys.exit(1)

    return vm_mobs

def login(args):
    """
    ServiceContentオブジェクトを返す。

    :rtype: class
    :return: pyVmomi.VmomiSupport.vim.ServiceInstanceContent
    """
    # SSL証明書対策
    context = None
    if hasattr(ssl, '_create_unverified_context'):
        context = ssl._create_unverified_context()

    # 接続
    try:
        si = SmartConnect(host = args.host,
                          user = args.username,
                          pwd = args.password,
                          sslContext = context)
    except Exception as error:
        sys.stderr.write('vCenter Login process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
        sys.stderr.write('error msg: ' + colors.RED + error.msg + colors.END + '\n')
        sys.exit(1)
    else:
        sys.stdout.write('vCenter Login process...'.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')

    # 処理完了時にvCenterから切断
    atexit.register(Disconnect, si)

    # ServiceContent(Data Object)を取得
    content = si.content

    return content

def check_vmware_tools_status(vm_mobs):
    """
    ゲストOSのVMware toolsのステータスを確認します。
    ゲストOSのVMware toolsステータスが起動していない場合は `vm_mobs` から削除して対象外にします。

    :type vm_mobs: list
    :param vm_mobs: Managed Objectのリスト

    :rtype: list
    :return: Management Objectのリストを返す
    """
    for vm_mob in vm_mobs:
        vmware_tools_status = vm_mob.guest.toolsStatus
        if(not(vmware_tools_status == 'toolsOk')):
            sys.stderr.write('error msg: ' + colors.RED + 'VMware tools of ' + vm_mob.name + ' is not working.' + colors.END + '\n')
            vm_mobs.remove(vm_mob)

    return vm_mobs

def check_save_file(save_file, t, args):
    """
    ダウンロードするファイルの保存先に同じファイル名が存在するか確認します。
    """
    if(os.path.exists(save_file)):
        sys.stdout.write('[%s] file exists in the file save destination.\n' % t)
        if(args.overwrite):
            sys.stdout.write('file overwrite.\n')
        else:
            sys.stderr.write('error msg: ' + colors.RED + 'stop processing.' + colors.END + '\n')
            sys.exit(1)
    else:
        # 保存先パスが存在しない場合はVM名のディレクトリを作成する
        path, file = os.path.split(save_file)
        if(not(os.path.isdir(path))):
            os.makedirs(path)

def check_upload_file(upload_file):
    """
    アップロードするファイルの存在確認をします。
    """
    if(not(os.path.exists(upload_file))):
        sys.stderr.write('error msg: ' + colors.RED + 'file to be uploaded does not exist.' + colors.END + '\n')
        sys.exit(1)

def download(args):
    """
    Guestからファイルをダウンロードする。
    """
    class downloadThread(threadJob):
        def run(self):
            # ゲストOSアカウント設定
            guest_auth = vim.vm.guest.NamePasswordAuthentication()
            guest_auth.username = self.args.guestuser
            guest_auth.password = self.args.guestpassword

            # Guestからダウンロードするファイル情報を取得
            try:
                r = self.content.guestOperationsManager.fileManager.InitiateFileTransferFromGuest(
                    vm=self.vm_mob,
                    auth=guest_auth,
                    guestFilePath=self.args.downloadpath
                )
            except Exception as error:
                msg = 'downloading file from %s process...' % self.vm_mob.name
                sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                sys.stderr.write('error msg: '.rjust(15) + colors.RED + error.msg + colors.END + '\n')
                sys.exit(1)

            # ファイルのダウンロード
            r = requests.get(r.url, stream=True, verify=False)
            if(r.status_code == 200):
                msg = 'download file from %s' % self.vm_mob.name
                with open(self.save_file, 'wb') as f:
                    total_length = int(r.headers.get('content-length'))
                    for chunk in progress.bar(r.iter_content(chunk_size=1024), expected_size=(total_length/1024 + 1), label=msg.ljust(40)):
                        if chunk:
                            f.write(chunk)
                            f.flush()
            else:
                msg = 'downloading file from %s process...' % self.vm_mob.name
                sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                sys.stderr.write('error msg: '.rjust(15) + colors.RED + 'GET request did not succeed.' + colors.END + '\n')
                sys.exit(1)

    def main(args):
        # ファイルの存在確認
        save_file_map = {}
        for t in args.targetvm:
            path, file = os.path.split(args.savepath)
            save_file = os.path.join(path, t, file)
            check_save_file(save_file, t, args)
            save_file_map[t] = save_file

        # ServiceContent.
        content = login(args)

        # 仮想インスタンスのmobを取得
        vm_mobs = get_mob_info(content, vim.VirtualMachine, args.targetvm)
        check_vmware_tools_status(vm_mobs)

        # マルチスレッド
        threads = []
        for vm_mob in vm_mobs:
            t = downloadThread()
            t.save_file = save_file_map[vm_mob.name]
            t.args = args
            t.vm_mob = vm_mob
            t.content = content
            t.start()
            threads.append(t)

            # Max Thread確認
            if (len(threads) >= args.max_thread):
                while True:
                    for t in threads:
                        if (not (t.is_alive())):
                            threads.remove(t)
                    if (len(threads) < args.max_thread):
                        break
                    time.sleep(1)

    main(args)

def upload(args):
    """
    Guestへファイルをアップロードする。
    """
    class uploadThread(threadJob):
        def run(self): # ゲストOSアカウント設定
            guest_auth = vim.vm.guest.NamePasswordAuthentication()
            guest_auth.username = self.args.guestuser
            guest_auth.password = self.args.guestpassword

            # Guestへアップロードするファイル情報を取得
            upload_file_size = os.path.getsize(self.upload_file)
            try:
                r = self.content.guestOperationsManager.fileManager.InitiateFileTransferToGuest(
                    vm=self.vm_mob,
                    auth=guest_auth,
                    guestFilePath=self.args.savepath,
                    fileAttributes=vim.vm.guest.FileManager.FileAttributes(),
                    fileSize=upload_file_size,
                    overwrite=self.args.overwrite
                )
            except Exception as error:
                msg = '%s file upload process...' % self.vm_mob.name
                sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                sys.stderr.write('error msg: '.rjust(15) + colors.RED + error.msg + colors.END + '\n')
                sys.exit(1)

            # ファイルのアップロード
            msg = '%s file upload process start...\r' % self.vm_mob.name
            sys.stdout.write(msg)
            with open(self.upload_file, 'rb') as f:
                data = f.read()
                r = requests.put(r, data=data, verify=False)
                if(r.status_code == 200):
                    msg = '%s file upload process...' % self.vm_mob.name
                    sys.stdout.write(msg.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')

                    # コマンド実行する場合
                    if(self.args.cmd):
                        guest_program_spec = vim.vm.guest.ProcessManager.ProgramSpec()
                        guest_program_spec.arguments = self.args.cmd_args if(self.args.cmd_args) else ''
                        guest_program_spec.programPath = self.args.cmd
                        try:
                            r = self.content.guestOperationsManager.processManager.StartProgramInGuest(
                                vm=self.vm_mob,
                                auth=guest_auth,
                                spec=guest_program_spec
                            )
                        except Exception as error:
                            msg = '%s command execute process...' % self.vm_mob.name
                            sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                            sys.stderr.write('error msg: '.rjust(15) + colors.RED + error.msg + colors.END + '\n')
                            sys.exit(1)

                        # 実行したプロセスの終了を待つ
                        while True:
                            try:
                                r = self.content.guestOperationsManager.processManager.ListProcessesInGuest(
                                    vm=self.vm_mob,
                                    auth=guest_auth
                                )
                            except Exception as error:
                                msg = '%s pid check process...' % self.vm_mob.name
                                sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                                sys.stderr.write('error msg: '.rjust(15) + colors.RED + error.msg + colors.END + '\n')
                                sys.exit(1)

                            pid_num = [ x for x in r if(re.search(r'%s.*%s' % (self.args.cmd, self.args.cmd_args), x.cmdLine)) ]
                            if(pid_num):
                                msg = '%s processing in process...' % self.vm_mob.name
                                sys.stdout.write(msg + '\r')
                                exitCode = pid_num.pop().exitCode
                                if(isinstance(exitCode, int)):
                                    msg = '%s command execute finish' % self.vm_mob.name
                                    if(exitCode == 0):
                                        sys.stdout.write(msg.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')
                                        break
                                    else:
                                        sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                                        sys.stderr.write('exit code: '.rjust(15) + colors.RED + str(exitCode) + colors.END + '\n')
                                        break

                            time.sleep(1)
                else:
                    msg = '%s file upload process...' % self.vm_mob.name
                    sys.stderr.write(msg.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                    sys.stderr.write('error msg: '.rjust(15) + colors.RED + 'POST request did not succeed.' + colors.END + '\n')
                    sys.exit(1)

    def main(args):
        # ファイルの存在確認
        upload_file = args.uploadpath
        check_upload_file(upload_file)

        # ServiceContent.
        content = login(args)

        # 仮想インスタンスのmobを取得
        vm_mobs = get_mob_info(content, vim.VirtualMachine, args.targetvm)
        vm_mobs = check_vmware_tools_status(vm_mobs)

        # マルチスレッド
        threads = []
        for vm_mob in vm_mobs:
            t = uploadThread()
            t.upload_file = upload_file
            t.args = args
            t.vm_mob = vm_mob
            t.content = content
            t.start()
            threads.append(t)

            # Max Thread確認
            if(len(threads) >= args.max_thread):
                while True:
                    for t in threads:
                        if(not(t.is_alive())):
                            threads.remove(t)
                    if(len(threads) < args.max_thread):
                        break
                    time.sleep(1)

    main(args)

if __name__ == "__main__":
    options()
