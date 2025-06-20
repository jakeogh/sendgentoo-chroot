#!/usr/bin/env python3
# -*- coding: utf8 -*-

# pylint: disable=useless-suppression             # [I0021]
# pylint: disable=missing-docstring               # [C0111] docstrings are always outdated and wrong
# pylint: disable=missing-param-doc               # [W9015]
# pylint: disable=missing-module-docstring        # [C0114]
# pylint: disable=fixme                           # [W0511] todo encouraged
# pylint: disable=line-too-long                   # [C0301]
# pylint: disable=too-many-instance-attributes    # [R0902]
# pylint: disable=too-many-lines                  # [C0302] too many lines in module
# pylint: disable=invalid-name                    # [C0103] single letter var names, name too descriptive
# pylint: disable=too-many-return-statements      # [R0911]
# pylint: disable=too-many-branches               # [R0912]
# pylint: disable=too-many-statements             # [R0915]
# pylint: disable=too-many-arguments              # [R0913]
# pylint: disable=too-many-nested-blocks          # [R1702]
# pylint: disable=too-many-locals                 # [R0914]
# pylint: disable=too-many-public-methods         # [R0904]
# pylint: disable=too-few-public-methods          # [R0903]
# pylint: disable=no-member                       # [E1101] no member for base
# pylint: disable=attribute-defined-outside-init  # [W0201]
# pylint: disable=too-many-boolean-expressions    # [R0916] in if statement

from __future__ import annotations

import logging
import os
import subprocess
import sys
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

logging.basicConfig(level=logging.INFO)
signal(SIGPIPE, SIG_DFL)


if len(sys.argv) <= 2:
    print(sys.argv[0], "arguments required")
    sys.exit(1)


def syscmd(cmd):
    print(cmd, file=sys.stderr)
    os.system(cmd)


import signal
import time
import traceback


# Signal handler for SIGINT (Ctrl+C) and SIGTERM
def signal_handler(sig, frame):
    print(f"\nReceived signal {sig}. Pausing before exit...")
    print("Stack trace:")
    traceback.print_stack(frame)
    time.sleep(5)  # Pause for 5 seconds
    sys.exit(1)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

syscmd("emerge dev-python/sh -1")
import sh


def emerge_force(packages):
    _env = os.environ.copy()
    _env["CONFIG_PROTECT"] = "-*"

    emerge_command = sh.emerge.bake(
        "--with-bdeps=y",
        "--quiet",
        "-v",
        "--tree",
        "--usepkg=n",
        "--ask",
        "n",
        "--autounmask",
        "--autounmask-write",
    )

    for package in packages:
        print("emerge_force() package:", package, file=sys.stderr)
        emerge_command = emerge_command.bake(package)
        print("emerge_command:", emerge_command, file=sys.stderr)

    emerge_command(
        "-p",
        _ok_code=[0, 1],
        _env=_env,
        _out=sys.stdout,
        _err=sys.stderr,
    )
    emerge_command(
        "--autounmask-continue",
        _env=_env,
        _out=sys.stdout,
        _err=sys.stderr,
    )


if not os.environ.get("TMUX"):
    print("Not running in tmux. Installing tmux...")
    # with open("/root/.tmux.conf", "a", encoding="utf8") as fh:
    #    fh.write("\nset-option remain-on-exit on\n")

    syscmd("emerge app-misc/tmux -u")
    script_name = os.path.basename(__file__)
    script_path = os.path.realpath(__file__)
    print(
        f"Not running in tmux. Launching new tmux session...{script_path=} {sys.argv[1:]}"
    )
    # Launch new tmux session running this script
    # subprocess.run(['tmux', 'new-session', '-s', script_name, 'python3', script_name])
    # sh.tmux("-L", "sendgentoo", "start-server")
    sh.tmux("-L", "sendgentoo", "new-session", "-d", "-s", "bootstrap")
    time.sleep(3)
    os.system("ls -al /tmp/tmux-0/")
    sh.tmux("-L", "sendgentoo", "set-option", "-g", "remain-on-exit", "failed")
    cmd = [
        "tmux",
        "-L",
        "sendgentoo",
        "new-session",
        "-s",
        "myscript",
        "python3",
        script_path,
    ] + sys.argv[1:]
    # cmd.extend(["; /bin/bash -l"])
    print(f"{cmd=}")
    print(f"{' '.join(cmd)=}")
    subprocess.run(cmd)
    sys.exit(0)

print("Running inside tmux!")
print("Arguments received:", sys.argv[1:])

try:
    print("os.environ['TMUX']:", os.environ["TMUX"])
except KeyError:
    print("start tmux!", file=sys.stderr)
    sys.exit(1)


syscmd("eselect news read all")

try:
    with open("/etc/portage/proxy.conf", "r", encoding="utf8") as fh:
        for line in fh:
            line = line.strip()
            line = "".join(line.split('"'))
            line = "".join(line.split("#"))
            if line:
                # icp(line)
                key = line.split("=")[0]
                value = line.split("=")[1]
                os.environ[key] = value
except FileNotFoundError:
    pass

syscmd("emerge --quiet dev-vcs/git -1 -u")
syscmd("emerge --sync")
# needed below!
syscmd(
    "emerge --quiet sys-apps/portage dev-python/click app-eselect/eselect-repository -1 -u"
)

os.makedirs("/etc/portage/repos.conf", exist_ok=True)
if "jakeogh" not in sh.eselect("repository", "list", "-i"):
    sh.eselect(
        "repository",
        "add",
        "jakeogh",
        "git",
        "https://github.com/jakeogh/jakeogh",
        _out=sys.stdout,
        _err=sys.stderr,
    )  # ignores http_proxy
sh.emaint("sync", "-r", "jakeogh", _out=sys.stdout, _err=sys.stderr)  # this needs git


def enable_repository(repo: str):
    if repo not in sh.eselect("repository", "list", "-i"):  # for fchroot (next time)
        sh.eselect(
            "repository",
            "enable",
            repo,
            _out=sys.stdout,
            _err=sys.stderr,
        )  # ignores http_proxy
    sh.emaint("sync", "-r", repo, _out=sys.stdout, _err=sys.stderr)  # this needs git


# enable_repository(repo='guru') # types-requests
enable_repository(repo="pentoo")  # fchroot
enable_repository(repo="natinst")  # dev-python/PyVISA-py
enable_repository(
    repo="slonko"
)  # dev-python/convertdate and its dep dev-python/pymeeus to make dev-python/dateparser-9999::jakeogh happy, which portagetool below depends on


emerge_force(["dev-python/portagetool"])
emerge_force(["dev-python/asserttool"])
emerge_force(["dev-python/boottool"])
emerge_force(["dev-python/compile-kernel"])
emerge_force(["dev-python/icecream"])
emerge_force(["dev-python/smarttool"])  # /etc/local.d/all_block_devices_passed.start
emerge_force(["app-misc/resolve-march-native"])  # for /etc/portage/cflags.conf

# todo, move this to post_reboot, and make some kind of global /.native check
emerge_force(["portage-set-compile-flags-on-boot"])

# emerge_force(["portage-set-cflags-on-boot"])
# not until reboot
# os.system("/home/sysskel/etc/local.d/portage_set_cflags.start")

# emerge_force(["portage-set-cpu-flags-on-boot"])
# not until reboot
# os.system("/home/sysskel/etc/local.d/portage_set_cpu_flags.start")

emerge_force(["portage-set-emerge-default-opts-on-boot"])
os.system("/home/sysskel/etc/local.d/portage_set_emerge_default_opts.start")

emerge_force(["portage-set-makeopts-on-boot"])
os.system("/home/sysskel/etc/local.d/portage_set_makeopts.start")


from pathlib import Path

import click
from asserttool import ic
from asserttool import icp
from boottool import install_grub
from clicktool import click_add_options
from clicktool import click_global_options
from clicktool import tvicgvd
from eprint import eprint
from globalverbose import gvd
from mounttool import path_is_mounted
from pathtool import gurantee_symlink
from pathtool import write_line_to_file
from portagetool import add_accept_keyword
from portagetool import install_packages


@click.command()
@click.option(
    "--stdlib",
    is_flag=False,
    required=False,
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option("--boot-device", is_flag=False, required=True)
@click.option(
    "--march", is_flag=False, required=True, type=click.Choice(["native", "nocona"])
)
@click.option("--newpasswd", is_flag=False, required=True)
@click.option("--pinebook-overlay", is_flag=True, required=False)
@click.option(
    "--kernel",
    is_flag=False,
    required=True,
    type=click.Choice(["gentoo-sources", "pinebookpro-manjaro-sources"]),
    default="gentoo-sources",
)
@click.option("--configure-kernel", is_flag=True)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
    stdlib: str,
    boot_device: Path,
    march: str,
    newpasswd: str,
    pinebook_overlay: bool,
    configure_kernel: bool,
    kernel: str,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
):
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    # musl: http://distfiles.gentoo.org/experimental/amd64/musl/HOWTO
    # spark: https://github.com/holman/spark.git
    # export https_proxy="http://192.168.222.100:8888"
    # export http_proxy="http://192.168.222.100:8888"
    # source /home/cfg/_myapps/sendgentoo/sendgentoo/utils.sh
    icp(
        stdlib,
        boot_device,
        march,
        newpasswd,
        pinebook_overlay,
        kernel,
    )

    assert path_is_mounted(Path("/boot/efi"))

    # sh.emerge('--sync', _out=sys.stdout, _err=sys.stderr)

    os.makedirs(Path("/var/db/repos/gentoo"), exist_ok=True)

    if stdlib == "musl":
        if "musl" not in sh.eselect(
            "repository", "list", "-i"
        ):  # for fchroot (next time)
            sh.eselect(
                "repository", "enable", "musl", _out=sys.stdout, _err=sys.stderr
            )  # ignores http_proxy
        sh.emaint(
            "sync", "-r", "musl", _out=sys.stdout, _err=sys.stderr
        )  # this needs git

    # otherwise gcc compiles twice
    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("package.use") / Path("gcc"),
        line="sys-devel/gcc fortran\n",
        unique=True,
    )

    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("package.mask") / Path("rust"),
        line="dev-lang/rust-bin\n",
        unique=True,
    )

    install_packages(
        ["netdate"],
        force=False,
    )
    sh.date(_out=sys.stdout, _err=sys.stderr)
    sh.netdate(
        "time.nist.gov", _out=sys.stdout, _err=sys.stderr, _ok_code=[0, 1]
    )  # todo, figure out NTP over proxy
    sh.date(_out=sys.stdout, _err=sys.stderr)

    sh.emerge("-uvNDq", "@world", _out=sys.stdout, _err=sys.stderr)

    # zfs_module_mode = "module"
    # env-update || exit 1
    # source /etc/profile || exit 1

    # here down is stuff that might not need to run every time
    # ---- begin run once, critical stuff ----

    sh.passwd("-d", "root")
    if Path("/home/sysskel/etc/local.d/").exists():
        sh.chmod("+x", "-R", "/home/sysskel/etc/local.d/")
    # sh.eselect('python', 'list')  # depreciated
    sh.eselect("profile", "list", _out=sys.stdout, _err=sys.stderr)
    write_line_to_file(
        path=Path("/etc") / Path("locale.gen"),
        line="en_US.UTF-8 UTF-8\n",
        unique=True,
    )
    sh.locale_gen(
        _out=sys.stdout, _err=sys.stderr
    )  # hm, musl does not need this? dont fail here for uclibc or musl

    write_line_to_file(
        path=Path("/etc") / Path("env.d") / Path("02collate"),
        line='LC_COLLATE="C"\n',
        unique=True,
    )

    # not /etc/localtime, the next command does that
    write_line_to_file(
        path=Path("/etc") / Path("timezone"),
        line="US/Arizona\n",
        unique=True,
    )

    sh.emerge("--config", "timezone-data")
    sh.grep("processor", "/proc/cpuinfo")

    cores = len(sh.grep("processor", "/proc/cpuinfo").splitlines())
    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("makeopts.conf"),
        line=f'MAKEOPTS="-j{cores}"\n',
        unique=True,
    )

    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("cflags.conf"),
        line=f'CFLAGS="-march={march} -O2 -pipe -ggdb"\n',
        unique=True,
    )

    # right here, portage needs to get configured... this stuff ends up at the end of the final make.conf
    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("make.conf"),
        line='ACCEPT_KEYWORDS="~amd64"\n',
        unique=True,
    )

    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("make.conf"),
        line='EMERGE_DEFAULT_OPTS="--quiet-build=y --tree --nospinner"\n',
        unique=True,
    )

    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("make.conf"),
        line='FEATURES="parallel-fetch splitdebug"\n',
        unique=True,
    )

    # source /etc/profile

    # works, but quite a delay for an installer
    # install_packages(['gcc'], )
    # sh.gcc_config('latest', _out=sys.stdout, _err=sys.stderr)

    # install kernel and update symlink (via use flag)
    os.environ["KCONFIG_OVERWRITECONFIG"] = (
        "1"  # https://www.mail-archive.com/lede-dev@lists.infradead.org/msg07290.html
    )

    # required so /usr/src/linux exists
    kernel_package_use = (
        Path("/etc") / Path("portage") / Path("package.use") / Path(kernel)
    )
    write_line_to_file(
        path=kernel_package_use,
        line=f"sys-kernel/{kernel} symlink\n",
        unique=True,
    )

    add_accept_keyword(
        "sys-fs/zfs-9999",
    )
    add_accept_keyword(
        "sys-fs/zfs-kmod-9999",
    )

    # memtest86+ # do before generating grub.conf
    # bug, /boot isnt even mounted
    #        "memtest86+",
    # do this in compile-kernel instead
    install_packages(
        [
            f"sys-kernel/{kernel}",
            "dev-debug/strace",
            "app-text/wgetpaste",
            "dhcpcd",
        ],
        force=False,
        upgrade_only=True,
    )
    os.truncate(kernel_package_use, 0)  # dont leave symlink USE flag in place

    # try:
    #    sh.grep("CONFIG_TRIM_UNUSED_KSYMS is not set", "/usr/src/linux/.config")
    # except sh.ErrorReturnCode_1 as e:
    #    icp(e)
    #    eprint("ERROR: Rebuild the kernel with CONFIG_TRIM_UNUSED_KSYMS must be =n")
    #    sys.exit(1)

    # try:
    #    sh.grep("CONFIG_FB_EFI is not set", "/usr/src/linux/.config", _ok_code=[1])
    # except sh.ErrorReturnCode_1 as e:
    #    icp(e)
    #    eprint("ERROR: Rebuild the kernel with CONFIG_FB_EFI=y")
    #    sys.exit(1)

    write_line_to_file(
        path=Path("/etc") / Path("fstab"),
        line="#<fs>\t<mountpoint>\t<type>\t<opts>\t<dump/pass>\n",
        unique=False,
        unlink_first=True,
    )

    install_packages(
        ["gradm"],
        force=False,
    )  # required for gentoo-hardened RBAC

    # required for genkernel
    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("package.use") / Path("util-linux"),
        line="sys-apps/util-linux static-libs\n",
        unique=False,
        unlink_first=True,
    )

    write_line_to_file(
        path=Path("/etc") / Path("portage") / Path("package.license"),
        line="sys-kernel/linux-firmware linux-fw-redistributable no-source-code\n",
        unique=True,
        unlink_first=False,
    )

    install_packages(
        ["genkernel"],
        force=False,
    )
    os.makedirs("/etc/portage/repos.conf", exist_ok=True)

    if Path("/etc/portage/proxy.conf").exists():
        with open("/etc/portage/proxy.conf", "r", encoding="utf8") as fh:
            for line in fh:
                line = line.strip()
                line = "".join(line.split('"'))
                line = "".join(line.split("#"))
                if line:
                    icp(line)
                    # key = line.split("=")[0]
                    # value = line.split("=")[1]
                    # os.environ[key] = value    # done at top of file
                    write_line_to_file(
                        path=Path("/etc") / Path("wgetrc"),
                        line=f"{line}\n",
                        unique=True,
                        unlink_first=False,
                    )

    write_line_to_file(
        path=Path("/etc") / Path("wgetrc"),
        line="use_proxy = on\n",
        unique=True,
        unlink_first=False,
    )

    if pinebook_overlay:
        if "pinebookpro-overlay" not in sh.eselect("repository", "list", "-i"):
            sh.eselect(
                "repository",
                "add",
                "pinebookpro-overlay",
                "git",
                "https://github.com/Jannik2099/pinebookpro-overlay.git",
            )  # ignores http_proxy
        sh.emerge("--sync", "pinebookpro-overlay")
        sh.emerge("-u", "pinebookpro-profile-overrides")

    install_packages(
        ["compile-kernel"],
        force=True,
    )  # requires jakeogh overlay
    compile_kernel_command = sh.compile_kernel.bake("compile-and-install")
    compile_kernel_command = compile_kernel_command.bake("--no-check-boot")
    if configure_kernel:
        compile_kernel_command = compile_kernel_command.bake("--configure")
    # compile_kernel_command(_out=sys.stdout, _err=sys.stderr, _ok_code=[0])

    # compile_kernel_command_str = f"{compile_kernel_command.path} {' '.join(compile_kernel_command._partial_baked_args)}"
    compile_kernel_command_str = f"{compile_kernel_command}"
    eprint(f"{compile_kernel_command_str=}")
    _exit_status = os.WEXITSTATUS(os.system(compile_kernel_command_str))
    if _exit_status != 0:
        raise ValueError(f"{compile_kernel_command_str=} exited: {_exit_status=}")

    # this cant be done until memtest86+ and the kernel are ready
    install_grub(
        boot_device=boot_device,
        skip_uefi=False,
        debug_grub=False,
    )

    sh.rc_update(
        "add", "zfs-mount", "boot", _out=sys.stdout, _err=sys.stderr, _ok_code=[0, 1]
    )  # dont exit if this fails

    gurantee_symlink(
        relative=False,
        target=Path("/etc/init.d/net.lo"),
        link_name=Path("/etc/init.d/net.eth0"),
    )
    sh.rc_update("add", "net.eth0", "default", _out=sys.stdout, _err=sys.stderr)

    install_packages(
        ["gpm"],
        force=False,
        upgrade_only=True,
    )
    sh.rc_update(
        "add", "gpm", "default", _out=sys.stdout, _err=sys.stderr
    )  # console mouse support

    # install_packages('elogind')
    # rc-update add elogind default

    install_packages(
        ["app-admin/sysklogd"],
        force=False,
        upgrade_only=True,
    )
    sh.rc_update(
        "add", "sysklogd", "default", _out=sys.stdout, _err=sys.stderr
    )  # syslog-ng hangs on boot... bloated

    os.makedirs("/etc/portage/package.mask", exist_ok=True)
    install_packages(
        ["unison"],
        force=False,
        upgrade_only=True,
    )
    # sh.eselect('unison', 'list') #todo

    # sh.perl_cleaner('--reallyall', _out=sys.stdout, _err=sys.stderr)  # perhaps in post_reboot instead, too slow

    # sys_apps/usbutils is required for boot scripts that use lsusb
    # dev-python/distro  # distro detection in boot scripts
    # dev-util/ctags     # so vim/nvim wont complain
    # sys-process/glances  # needs rust
    install_packages(
        [
            "app-admin/sudo",
            "sys-apps/smartmontools",
            "app-portage/gentoolkit",
            "sys-power/powertop",
            "sys-power/upower",
            "sys-apps/dmidecode",
            "app-editors/vim",
            "net-misc/openssh",
            "www-client/links",
            "sys-fs/safecopy",
            "sys-process/lsof",
            "sys-apps/lshw",
            "app-editors/hexedit",
            "app-admin/pydf",
            "sys-fs/ncdu",
            "sys-process/htop",
            "sys-fs/ddrescue",
            "sys-fs/dd-rescue",
            "net-dns/bind-tools",
            "sys-fs/bindfs",
            "app-admin/sysstat",
            "net-wireless/wpa_supplicant",
            "sys-apps/sg3_utils",
            "sys-fs/multipath-tools",
            "sys-apps/usbutils",
            "net-fs/nfs-utils",
            "dev-python/distro",
            "app-misc/tmux",
            "dev-util/ccache",
            "dev-util/ctags",
            "sys-apps/moreutils",
            "app-misc/screen",
            "app-portage/smart-live-rebuild",
            "net-print/cups-meta",
        ],
        force=True,
        upgrade_only=True,
    )

    install_packages(
        ["dev-util/fatrace"],
        force=True,
        upgrade_only=True,
    )  # jakeogh overlay fatrace-9999 (C version)
    install_packages(
        ["dev-python/replace-text"],
        force=True,
    )
    sh.rc_update("add", "smartd", "default")
    sh.rc_update("add", "nfs", "default")

    sh.rc_update("add", "dbus", "default")

    os.makedirs("/var/cache/ccache", exist_ok=True)
    sh.chown("root:portage", "/var/cache/ccache")
    sh.chmod("2775", "/var/cache/ccache")

    # sh.ls('/etc/ssh/sshd_config', '-al', _out=sys.stdout, _err=sys.stderr)

    write_line_to_file(
        path=Path("/etc") / Path("ssh") / Path("sshd_config"),
        line="PermitRootLogin yes\n",
        unique=True,
        unlink_first=False,
    )

    os.environ["LANG"] = "en_US.UTF8"  # to make click happy

    write_line_to_file(
        path=Path("/etc") / Path("inittab"),
        line="PermitRootLogin yes\n",
        unique=True,
        unlink_first=False,
    )

    with open("/etc/inittab", "r", encoding="utf8") as fh:
        if "noclear" not in fh.read():
            sh.replace_text(
                "--match",
                "c1:12345:respawn:/sbin/agetty 38400 tty1 linux",
                "--replacement",
                "c1:12345:respawn:/sbin/agetty 38400 tty1 linux --noclear",
                "/etc/inittab",
            )

    install_packages(
        ["dev-python/sendgentoo-post-reboot"],
        force=True,
    )

    install_packages(
        ["dev-python/portagetool"],
        force=True,
    )

    eprint("sendgentoo_post_chroot.py complete! Exit chroot and reboot.")
    _ans = input("Press enter to exit sendgentoo_post_chroot.py")


if __name__ == "__main__":
    try:
        # pylint: disable=E1120
        cli()
    except SystemExit:
        # Handle SystemExit separately to respect signal handler exit
        raise
    except Exception as e:
        # Catch any unexpected exceptions in main
        print(f"Unexpected error: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()
        print("waiting for ENTER to exit")
        time.sleep(5)
        input("press enter to exit")
        sys.exit(1)
