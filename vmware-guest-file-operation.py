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
import requests
# requestsの自己証明書の警告を出力しないようにする
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
__license__ = 'MIT'

class colors:
    GREEN = '\033[32m'
    RED = '\033[91m'
    END = '\033[0m'

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
                        type=str, required=True,
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
    parser_upload.add_argument('--wait-execute-process', '-wproc',
                               action='store_true',
                               help='ファイルアップロード後に実行したコマンドの終了を')
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
    """
    r = content.viewManager.CreateContainerView(content.rootFolder,
                                                [mob],
                                                True)

    # 返すmobを名前で指定する場合
    vm_mob = ''
    if(target):
        for i in r.view:
            if(i.name == target):
                vm_mob = i
                break

    if(not(vm_mob)):
        sys.stderr.write('error msg: ' + colors.RED + target + ' not found.' + colors.END + '\n')
        sys.exit(1)

    return vm_mob

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

def check_vmware_tools_status(vm_mob):
    """
    ゲストOSのVMware toolsのステータスを確認します。
    """
    vmware_tools_status = vm_mob.guest.toolsStatus
    if(not(vmware_tools_status == 'toolsOk')):
        sys.stderr.write('error msg: ' + colors.RED + 'VMware tools of ' + vm_mob.name + ' is not working.' + colors.END + '\n')
        sys.exit(1)

def check_save_file(save_file, args):
    """
    ダウンロードするファイルの保存先に同じファイル名が存在するか確認します。
    """
    if(os.path.exists(save_file)):
        sys.stdout.write('file exists in the file save destination.\n')
        if(args.overwrite):
            sys.stdout.write('file overwrite.\n')
        else:
            sys.stderr.write('error msg: ' + colors.RED + 'stop processing.' + colors.END + '\n')
            sys.exit(1)

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
    # ファイルの存在確認
    save_file = args.savepath
    check_save_file(save_file, args)

    # ServiceContent.
    content = login(args)

    # 仮想インスタンスのmobを取得
    vm_mob = get_mob_info(content, vim.VirtualMachine, args.targetvm)
    check_vmware_tools_status(vm_mob)

    # ゲストOSアカウント設定
    guest_auth = vim.vm.guest.NamePasswordAuthentication()
    guest_auth.username = args.guestuser
    guest_auth.password = args.guestpassword

    # Guestからダウンロードするファイル情報を取得
    try:
        r = content.guestOperationsManager.fileManager.InitiateFileTransferFromGuest(
                vm=vm_mob,
                auth=guest_auth,
                guestFilePath=args.downloadpath
            )
    except Exception as error:
        sys.stderr.write('file download process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
        sys.stderr.write('error msg: ' + colors.RED + error.msg + colors.END + '\n')
        sys.exit(1)

    # ファイルのダウンロード
    r = requests.get(r.url, stream=True, verify=False)
    if(r.status_code == 200):
        with open(args.savepath, 'wb') as f:
            total_length = int(r.headers.get('content-length'))
            for chunk in progress.bar(r.iter_content(chunk_size=1024), expected_size=(total_length/1024) + 1):
                if chunk:
                    f.write(chunk)
                    f.flush()
    else:
        sys.stderr.write('file download process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
        sys.stderr.write('error msg: ' + colors.RED + 'GET request did not succeed.' + colors.END + '\n')
        sys.exit(1)

def upload(args):
    """
    Guestへファイルをアップロードする。
    """
    # ファイルの存在確認
    upload_file = args.uploadpath
    check_upload_file(upload_file)

    # ServiceContent.
    content = login(args)

    # 仮想インスタンスのmobを取得
    vm_mob = get_mob_info(content, vim.VirtualMachine, args.targetvm)
    check_vmware_tools_status(vm_mob)

    # ゲストOSアカウント設定
    guest_auth = vim.vm.guest.NamePasswordAuthentication()
    guest_auth.username = args.guestuser
    guest_auth.password = args.guestpassword

    # Guestへアップロードするファイル情報を取得
    upload_file_size = os.path.getsize(upload_file)
    try:
        r = content.guestOperationsManager.fileManager.InitiateFileTransferToGuest(
                vm=vm_mob,
                auth=guest_auth,
                guestFilePath=args.savepath,
                fileAttributes=vim.vm.guest.FileManager.FileAttributes(),
                fileSize=upload_file_size,
                overwrite=args.overwrite
            )
    except Exception as error:
        sys.stderr.write('file upload process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
        sys.stderr.write('error msg: ' + colors.RED + error.msg + colors.END + '\n')
        sys.exit(1)

    # ファイルのアップロード
    with open(upload_file, 'rb') as f:
        data = f.read()
        r = requests.put(r, data=data, verify=False)
        if(r.status_code == 200):
            sys.stdout.write('file upload process...'.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')

            # コマンド実行する場合
            if(args.cmd):
                guest_program_spec = vim.vm.guest.ProcessManager.ProgramSpec()
                guest_program_spec.arguments = args.cmd_args if(args.cmd_args) else ''
                guest_program_spec.programPath = args.cmd
                try:
                    r = content.guestOperationsManager.processManager.StartProgramInGuest(
                        vm=vm_mob,
                        auth=guest_auth,
                        spec=guest_program_spec
                    )
                except Exception as error:
                    sys.stderr.write('command execute process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                    sys.stderr.write('error msg: ' + colors.RED + error.msg + colors.END + '\n')
                    sys.exit(1)
                else:
                    pid = str(r)
                    sys.stdout.write('command execute process...'.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')
                    sys.stdout.write('pid number: %s\n' % pid)

                    # 実行したプロセスの終了を待つ
                    if(args.wait_execute_process == True):
                        check_count = 0
                        fail_count = 0
                        while True:
                            try:
                                r = content.guestOperationsManager.processManager.ListProcessesInGuest(
                                    vm=vm_mob,
                                    auth=guest_auth
                                )
                            except Exception as error:
                                sys.stderr.write('pid check process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
                                sys.stderr.write('error msg: ' + colors.RED + error.msg + colors.END + '\n')
                                sys.exit(1)

                            pid_num = [ x for x in r if(re.search(r'%s %s' % (args.cmd, args.cmd_args), x.cmdLine)) ]
                            if(len(pid_num) >= 1 and check_count >= 0):
                                sys.stdout.write('Processing in progress...')
                                sys.stdout.flush()
                                sys.stdout.write('\r')
                                check_count += 1
                                time.sleep(1)
                            if(len(pid_num) == 0 and check_count == 0):
                                fail_count += 1
                                time.sleep(1)
                            if(len(pid_num) == 0 and check_count >= 1 or fail_count == 5):
                                sys.stdout.write('process finish....'.ljust(40) + '[' + colors.GREEN + 'success' + colors.END + ']\n')
                                break
        else:
            sys.stderr.write('file upload process...'.ljust(40) + '[' + colors.RED + 'failed' + colors.END + ']\n')
            sys.stderr.write('error msg: ' + colors.RED + 'POST request did not succeed.' + colors.END + '\n')
            sys.exit(1)

if __name__ == "__main__":
    options()
