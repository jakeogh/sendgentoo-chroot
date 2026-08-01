#!/usr/bin/env python3
# bootstrap script: runs inside a fresh stage3 chroot where only the stdlib
# exists, so imports of emerged packages happen mid-file after their emerges

import os
import signal
import subprocess
import sys
import time
import traceback

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

if len(sys.argv) <= 2:
    print(sys.argv[0], "arguments required", file=sys.stderr)
    sys.exit(1)


def _signal_handler(sig, frame) -> None:
    print(f"\nReceived signal {sig}. Pausing before exit...", file=sys.stderr)
    traceback.print_stack(frame)
    time.sleep(5)
    sys.exit(1)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def run(*cmd: str) -> None:
    print(" ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)


def run_capture(*cmd: str) -> str:
    print(" ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def proxy_conf_lines() -> list[str]:
    lines = []
    with open("/etc/portage/proxy.conf", "r", encoding="utf8") as fh:
        for line in fh:
            line = line.strip().replace('"', "").replace("#", "")
            if line:
                lines.append(line)
    return lines


if not os.environ.get("TMUX"):
    print("Not running in tmux. Installing tmux...")
    run("emerge", "app-misc/tmux", "-u")
    script_path = os.path.realpath(__file__)
    print(f"Launching new tmux session... {script_path=} {sys.argv[1:]}")
    run("tmux", "-L", "sendgentoo", "new-session", "-d", "-s", "bootstrap")
    time.sleep(3)
    subprocess.run(["ls", "-al", "/tmp/tmux-0/"], check=False)  # diagnostic
    run("tmux", "-L", "sendgentoo", "set-option", "-g", "remain-on-exit", "failed")
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
    print(f"{cmd=}")
    subprocess.run(cmd, check=True)
    sys.exit(0)

print("Running inside tmux!")
print("Arguments received:", sys.argv[1:])

try:
    print("os.environ['TMUX']:", os.environ["TMUX"])
except KeyError:
    print("start tmux!", file=sys.stderr)
    sys.exit(1)

run("eselect", "news", "read", "all")

if os.path.exists("/etc/portage/proxy.conf"):
    for _line in proxy_conf_lines():
        key, value = _line.split("=", maxsplit=1)
        os.environ[key] = value

run("emerge", "--quiet", "dev-vcs/git", "-1", "-u")
run("emerge", "--sync")
run(
    "emerge",
    "--quiet",
    "sys-apps/portage",
    "dev-python/click",
    "app-eselect/eselect-repository",
    "-1",
    "-u",
)

os.makedirs("/etc/portage/repos.conf", exist_ok=True)
if "jakeogh" not in run_capture("eselect", "repository", "list", "-i"):
    # ignores http_proxy
    run(
        "eselect",
        "repository",
        "add",
        "jakeogh",
        "git",
        "https://github.com/jakeogh/jakeogh",
    )
run("emaint", "sync", "-r", "jakeogh")  # needs git

# hs comes from the jakeogh overlay, so this cannot happen any earlier
run("emerge", "--quiet", "dev-python/hs", "-1", "-u")
import hs  # noqa: E402

_emerge = hs.Command("emerge")
_eselect = hs.Command("eselect")
_emaint = hs.Command("emaint")
_rc_update = hs.Command("rc-update")


def emerge_force(packages: list[str]) -> None:
    _env = os.environ.copy()
    _env["CONFIG_PROTECT"] = "-*"

    emerge_command = hs.Command("emerge")
    emerge_command.bake(
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
        emerge_command.bake(package)
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


def enable_repository(repo: str) -> None:
    if repo not in str(_eselect("repository", "list", "-i")):
        # ignores http_proxy
        _eselect("repository", "enable", repo, _out=sys.stdout, _err=sys.stderr)
    _emaint("sync", "-r", repo, _out=sys.stdout, _err=sys.stderr)  # needs git


enable_repository(repo="natinst")  # dev-python/PyVISA-py
# dev-python/convertdate and its dep dev-python/pymeeus to make
# dev-python/dateparser-9999::jakeogh happy, which portagetool depends on
enable_repository(repo="slonko")

emerge_force(["dev-python/portagetool"])
emerge_force(["dev-python/asserttool"])
emerge_force(["dev-python/filetool"])
emerge_force(["dev-python/boottool"])
emerge_force(["dev-python/compile-kernel"])
emerge_force(["dev-python/icecream"])
emerge_force(["dev-python/smarttool"])  # /etc/local.d/all_block_devices_passed.start

# cfg-layer supersedes the portage-set-*-on-boot packages: it detects cpu
# flags, cflags, makeopts and emerge opts into one file. Generated here rather
# than at first boot so this chroot's remaining emerges use the flags, and the
# source line is added first because a generated file nothing reads is worse
# than no file.
emerge_force(["app-portage/cfg-layer"])
_make_conf = "/etc/portage/make.conf"
_source_line = "source /etc/cfg-layer/autodetect.conf"
with open(_make_conf, encoding="utf8") as _mc:
    _existing = _mc.read()
if _source_line not in _existing.splitlines():
    # a stage3 make.conf need not end in a newline, and appending to a partial
    # line both hides the directive and defeats the check on the next run
    _separator = "" if _existing.endswith("\n") or not _existing else "\n"
    with open(_make_conf, "a", encoding="utf8") as _mc:
        _mc.write(f"{_separator}{_source_line}\n")
run("cfg-layer", "autodetect")


from pathlib import Path  # noqa: E402

import click  # noqa: E402
from asserttool import ic  # noqa: E402
from asserttool import icp  # noqa: E402
from boottool import install_grub  # noqa: E402
from clicktool import click_add_options  # noqa: E402
from clicktool import click_global_options  # noqa: E402
from clicktool import tvicgvd  # noqa: E402
from eprint import eprint  # noqa: E402
from filetool import append_line_to_file  # noqa: E402
from globalverbose import gvd  # noqa: E402
from mounttool import path_is_mounted  # noqa: E402
from portagetool import add_accept_keyword  # noqa: E402
from portagetool import install_packages  # noqa: E402


@click.command()
@click.option(
    "--stdlib",
    is_flag=False,
    required=False,
    type=click.Choice(["glibc", "musl"]),
)
@click.option(
    "--boot-device",
    is_flag=False,
    required=True,
    type=click.Path(
        exists=True,
        dir_okay=False,
        file_okay=True,
        allow_dash=False,
        path_type=Path,
    ),
)
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
    ctx: click.Context,
    stdlib: str,
    boot_device: Path,
    pinebook_overlay: bool,
    configure_kernel: bool,
    kernel: str,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    icp(
        stdlib,
        boot_device,
        pinebook_overlay,
        kernel,
    )

    assert path_is_mounted(Path("/boot/efi"))

    os.makedirs(Path("/var/db/repos/gentoo"), exist_ok=True)

    if stdlib == "musl":
        enable_repository(repo="musl")

    # otherwise gcc compiles twice
    append_line_to_file(
        path=Path("/etc/portage/package.use/gcc"),
        line="sys-devel/gcc fortran",
        unique=True,
    )

    append_line_to_file(
        path=Path("/etc/portage/package.mask/rust"),
        line="dev-lang/rust-bin",
        unique=True,
    )

    install_packages(
        ["netdate"],
        force=False,
    )
    hs.Command("date")(_out=sys.stdout, _err=sys.stderr)
    # todo, figure out NTP over proxy
    hs.Command("netdate")(
        "time.nist.gov",
        _out=sys.stdout,
        _err=sys.stderr,
        _ok_code=[0, 1],
    )
    hs.Command("date")(_out=sys.stdout, _err=sys.stderr)

    _emerge("-uvNDq", "@world", _out=sys.stdout, _err=sys.stderr)

    # first boot logs in on the console without a password, like the netboot
    # image; set credentials post-install
    hs.Command("passwd")("-d", "root", _out=sys.stdout, _err=sys.stderr)
    _eselect("profile", "list", _out=sys.stdout, _err=sys.stderr)

    append_line_to_file(
        path=Path("/etc/locale.gen"),
        line="en_US.UTF-8 UTF-8",
        unique=True,
    )
    # musl does not need this, but must not fail there either
    hs.Command("locale-gen")(_out=sys.stdout, _err=sys.stderr)

    append_line_to_file(
        path=Path("/etc/env.d/02collate"),
        line='LC_COLLATE="C"',
        unique=True,
    )

    # not /etc/localtime, the emerge --config below does that
    append_line_to_file(
        path=Path("/etc/timezone"),
        line="US/Arizona",
        unique=True,
    )
    _emerge("--config", "timezone-data")

    # this stuff ends up at the end of the final make.conf
    append_line_to_file(
        path=Path("/etc/portage/make.conf"),
        line='ACCEPT_KEYWORDS="~amd64"',
        unique=True,
    )
    append_line_to_file(
        path=Path("/etc/portage/make.conf"),
        line='FEATURES="parallel-fetch splitdebug"',
        unique=True,
    )

    # https://www.mail-archive.com/lede-dev@lists.infradead.org/msg07290.html
    os.environ["KCONFIG_OVERWRITECONFIG"] = "1"

    # required so /usr/src/linux exists
    kernel_package_use = Path("/etc/portage/package.use") / kernel
    append_line_to_file(
        path=kernel_package_use,
        line=f"sys-kernel/{kernel} symlink",
        unique=True,
    )

    add_accept_keyword("sys-fs/zfs-9999")
    add_accept_keyword("sys-fs/zfs-kmod-9999")

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

    Path("/etc/fstab").write_text(
        "#<fs>\t<mountpoint>\t<type>\t<opts>\t<dump/pass>\n", encoding="utf8"
    )

    install_packages(
        ["gradm"],
        force=False,
    )  # required for gentoo-hardened RBAC

    # required for genkernel
    Path("/etc/portage/package.use/util-linux").write_text(
        "sys-apps/util-linux static-libs\n", encoding="utf8"
    )

    append_line_to_file(
        path=Path("/etc/portage/package.license"),
        line="sys-kernel/linux-firmware linux-fw-redistributable no-source-code",
        unique=True,
    )

    install_packages(
        ["genkernel"],
        force=False,
    )
    os.makedirs("/etc/portage/repos.conf", exist_ok=True)

    if Path("/etc/portage/proxy.conf").exists():
        for _line in proxy_conf_lines():
            icp(_line)
            append_line_to_file(
                path=Path("/etc/wgetrc"),
                line=_line,
                unique=True,
            )

    append_line_to_file(
        path=Path("/etc/wgetrc"),
        line="use_proxy = on",
        unique=True,
    )

    if pinebook_overlay:
        if "pinebookpro-overlay" not in str(_eselect("repository", "list", "-i")):
            # ignores http_proxy
            _eselect(
                "repository",
                "add",
                "pinebookpro-overlay",
                "git",
                "https://github.com/Jannik2099/pinebookpro-overlay.git",
            )
        _emerge("--sync", "pinebookpro-overlay")
        _emerge("-u", "pinebookpro-profile-overrides")

    install_packages(
        ["compile-kernel"],
        force=True,
    )  # requires jakeogh overlay
    compile_kernel_command = hs.Command("compile-kernel")
    compile_kernel_command.bake("compile-and-install", "--no-check-boot")
    if configure_kernel:
        compile_kernel_command.bake("--configure")
    eprint(f"{compile_kernel_command=}")
    compile_kernel_command(_fg=True)

    # this cant be done until the kernel is ready
    install_grub(
        boot_device=boot_device,
        skip_uefi=False,
        debug_grub=False,
    )

    # dont exit if this fails
    _rc_update(
        "add",
        "zfs-mount",
        "boot",
        _out=sys.stdout,
        _err=sys.stderr,
        _ok_code=[0, 1],
    )

    net_eth0 = Path("/etc/init.d/net.eth0")
    net_eth0.unlink(missing_ok=True)
    net_eth0.symlink_to("/etc/init.d/net.lo")
    _rc_update("add", "net.eth0", "default", _out=sys.stdout, _err=sys.stderr)

    install_packages(
        ["gpm"],
        force=False,
        upgrade_only=True,
    )
    # console mouse support
    _rc_update("add", "gpm", "default", _out=sys.stdout, _err=sys.stderr)

    install_packages(
        ["app-admin/sysklogd"],
        force=False,
        upgrade_only=True,
    )
    # syslog-ng hangs on boot
    _rc_update("add", "sysklogd", "default", _out=sys.stdout, _err=sys.stderr)

    os.makedirs("/etc/portage/package.mask", exist_ok=True)
    install_packages(
        ["unison"],
        force=False,
        upgrade_only=True,
    )

    # sys-apps/usbutils is required for boot scripts that use lsusb
    # dev-python/distro: distro detection in boot scripts
    # dev-util/ctags: so vim/nvim wont complain
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
            "net-print/cups",
            "net-print/cups-meta",
            "sys-apps/ethtool",
            "sys-fs/dosfstools",
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
    _rc_update("add", "smartd", "default")
    _rc_update("add", "nfs", "default")
    _rc_update("add", "dbus", "default")

    os.makedirs("/var/cache/ccache", exist_ok=True)
    hs.Command("chown")("root:portage", "/var/cache/ccache")
    hs.Command("chmod")("2775", "/var/cache/ccache")

    append_line_to_file(
        path=Path("/etc/ssh/sshd_config"),
        line="PermitRootLogin yes",
        unique=True,
    )

    os.environ["LANG"] = "en_US.UTF8"  # to make click happy

    with open("/etc/inittab", "r", encoding="utf8") as fh:
        if "noclear" not in fh.read():
            hs.Command("replace-text")(
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
    input("Press enter to exit sendgentoo_post_chroot.py")


if __name__ == "__main__":
    cli()
