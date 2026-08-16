#!/usr/bin/env python3
# bootstrap script: runs inside a fresh stage3 chroot where only the stdlib
# exists, so imports of emerged packages happen mid-file after their emerges

import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

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


MAKE_CONF = "/etc/portage/make.conf"


def append_make_conf(line: str) -> None:
    # a stage3 make.conf need not end in a newline, and appending to a partial
    # line both hides the directive and defeats the check on the next run
    with open(MAKE_CONF, encoding="utf8") as fh:
        existing = fh.read()
    if line in existing.splitlines():
        return
    separator = "" if existing.endswith("\n") or not existing else "\n"
    with open(MAKE_CONF, "a", encoding="utf8") as fh:
        fh.write(f"{separator}{line}\n")
    print(f"{MAKE_CONF}: {line}", file=sys.stderr)


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


# Before any emerge: the target must resolve the same versions the server
# does, or it asks the deployment mirror for a distfile the server never
# fetched. Setting this in the command body below is too late -- everything
# merged during this module's bootstrap would resolve as stable.
append_make_conf('ACCEPT_KEYWORDS="~amd64"')

# No tmux here. The bootstrap already runs this whole install inside a tmux
# session in the deployment environment, and the chroot is entered with env -i,
# so TMUX is always unset and this always nested. The nested server's socket
# lives in the chroot's /tmp, which the outer session cannot reach, leaving a
# pane whose prefix key goes nowhere and which cannot be recovered once dead.
print("Arguments received:", sys.argv[1:], file=sys.stderr)

run("eselect", "news", "read", "all")

if os.path.exists("/etc/portage/proxy.conf"):
    for _line in proxy_conf_lines():
        key, value = _line.split("=", maxsplit=1)
        os.environ[key] = value

# no sync anywhere in here: every repository is bound in from the deployment
# environment with auto-sync off. A sync would reach for rsync or github and
# gemato would try a keyserver, none of which the target can resolve.
run("emerge", "--quiet", "dev-vcs/git", "-1", "-u")
run(
    "emerge",
    "--quiet",
    "sys-apps/portage",
    "dev-python/click",
    "app-eselect/eselect-repository",
    "-1",
    "-u",
)

assert Path("/var/db/repos/jakeogh").is_dir(), (
    "the jakeogh overlay is not bound into this chroot; the deployment "
    "environment must carry it"
)

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
    # bound in and declared in repos.conf by the chroot; nothing to enable and
    # nothing to sync. Asserted rather than skipped: a package that needs this
    # overlay fails far less clearly than the missing tree does.
    assert Path("/var/db/repos", repo).is_dir(), (
        f"repository {repo} is not bound into this chroot; add it to the "
        "deployment server so the image carries it"
    )


enable_repository(repo="natinst")  # dev-python/PyVISA-py

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
append_make_conf("source /etc/cfg-layer/autodetect.conf")
run("cfg-layer", "autodetect")

# the groups themselves arrive as a package, so nothing is copied into the
# target: sync materializes every managed file from what was merged here,
# including /etc/portage/patches
emerge_force(["app-portage/cfg-layer-groups"])
run("cfg-layer", "sync")



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
@click.option("--root-password", is_flag=False, required=False, default=None)
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
    root_password: None | str,
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

    # Seed the rust bootstrap before the world update. Every cargo consumer
    # depends on || ( dev-lang/rust dev-lang/rust-bin ), which lists source
    # first, so portage takes that branch and then has to bootstrap it: rust
    # 1.97 from 1.88 from 1.87 down to 1.81, which has no binary below it and
    # depends on itself. Portage prefers an already installed member of a ||
    # group, so installing the binary satisfies all of them at once.
    #
    # This script used to mask dev-lang/rust-bin, which is what made that
    # bootstrap mandatory: a masked package cannot satisfy a || group, so the
    # binary branch was never available. A rust cannot be compiled without a
    # rust, so masking the only entry point does not make the system build
    # from source, it makes the compiler unbuildable. Everything built with it
    # is still built here from source.
    _emerge("--quiet", "--noreplace", "dev-lang/rust-bin",
            _out=sys.stdout, _err=sys.stderr)

    _emerge("-uvNDq", "@world", _out=sys.stdout, _err=sys.stderr)

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
        enable_repository(repo="pinebookpro-overlay")
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

    # A drop-in, not an append. sshd takes the first value it obtains for a
    # keyword, and sshd_config includes sshd_config.d before the end of the
    # file, so anything appended after that Include loses to whatever the
    # distribution shipped -- gentoo-pam.conf sets PasswordAuthentication no,
    # which silently defeated an appended yes. Drop-ins are read in glob order,
    # so this name sorts ahead of them and wins.
    _sshd_dropin = Path("/etc/ssh/sshd_config.d/00-sendgentoo.conf")
    _sshd_dropin.parent.mkdir(parents=True, exist_ok=True)
    _sshd_dropin.write_text(
        "PermitRootLogin yes\nPasswordAuthentication yes\n", encoding="utf8"
    )
    _rc_update("add", "sshd", "default", _out=sys.stdout, _err=sys.stderr)

    if root_password:
        # Not -e, and not pre-hashed on the server: pambase configures
        # pam_unix for yescrypt, so a sha512 entry written into the shadow file
        # is not what this system's PAM produces, and login fails while passwd
        # reports success. chpasswd here uses whatever this system is
        # configured for. The password reaches it on stdin, never in an argv.
        hs.Command("chpasswd")(_in=f"root:{root_password}\n")
    else:
        hs.Command("passwd")("-d", "root", _out=sys.stdout, _err=sys.stderr)

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
