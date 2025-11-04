#!/usr/bin/env python3
# -*- coding: utf8 -*-

from __future__ import annotations

import os
import sys
from importlib import resources
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

import click
import sh
from asserttool import ic
from asserttool import icp
from asserttool import root_user
from boottool import make_hybrid_mbr
from click_auto_help import AHGroup
from clicktool import click_add_options
from clicktool import click_global_options
from clicktool import tvicgvd
from clicktool.mesa import click_mesa_options
from globalverbose import gvd
from mounttool import mount_something
from mounttool import path_is_mounted
from pathtool import write_line_to_file
from run_command import run_command
from with_chdir import chdir

signal(SIGPIPE, SIG_DFL)


def mount_for_chroot(*, ctx, mount_path: Path):
    mount_something(
        mountpoint=mount_path / Path("proc"),
        mount_type="proc",
        source=None,
        slave=False,
    )
    mount_something(
        mountpoint=mount_path / Path("sys"),
        mount_type="rbind",
        slave=True,
        source=Path("/sys"),
    )
    mount_something(
        mountpoint=mount_path / Path("dev"),
        mount_type="rbind",
        slave=True,
        source=Path("/dev"),
    )
    mount_something(
        mountpoint=mount_path / Path("run"),
        mount_type="bind",
        slave=True,
        source=Path("/run"),
    )

    os.makedirs(mount_path / Path("home") / Path("cfg"), exist_ok=True)

    os.makedirs(
        mount_path / Path("usr") / Path("local") / Path("portage"), exist_ok=True
    )

    os.system("emerge eprint")  # make sure /var/tmp/portage exists

    _var_tmp_portage = mount_path / Path("var") / Path("tmp") / Path("portage")
    os.makedirs(_var_tmp_portage, exist_ok=True)
    sh.chown("portage:portage", _var_tmp_portage)

    mount_something(
        mountpoint=_var_tmp_portage,
        mount_type="rbind",
        slave=False,
        source=Path("/var/tmp/portage"),
    )
    del _var_tmp_portage

    _gentoo_repo = (
        mount_path / Path("var") / Path("db") / Path("repos") / Path("gentoo")
    )
    _gentoo_repo.mkdir(exist_ok=True)
    mount_something(
        mountpoint=_gentoo_repo,
        mount_type="rbind",
        slave=False,
        source=Path("/var/db/repos/gentoo"),
    )
    del _gentoo_repo

    ctx.invoke(
        rsync_cfg,
        mount_path=mount_path,
    )


@click.group(no_args_is_help=True, cls=AHGroup)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
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


@cli.command()
@click.argument("mount_path")
@click_add_options(click_global_options)
@click.pass_context
def rsync_cfg(
    ctx,
    mount_path: str,
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

    if not root_user():
        ic("You must be root.")
        sys.exit(1)

    with chdir(
        "/home/",
    ):
        rsync_command = [
            "rsync",
            '--exclude="_priv"',
            '--exclude="_myapps/gentoo"',
            '--exclude="virt/iso"',
            "--one-file-system",
            "--delete",
            "--perms",
            "--executability",
            "--human-readable",
            "--recursive",
            "--links",
            "--times",
            f'/home/cfg "{mount_path}/home/"',
        ]
        run_command(
            " ".join(rsync_command),
            system=True,
            ask=False,
            verbose=True,
        )

    with resources.path(
        "sendgentoo_chroot", "sendgentoo_post_chroot.py"
    ) as _sendgentoo_post_chroot:
        icp(_sendgentoo_post_chroot)

        sh.cp(_sendgentoo_post_chroot, "/mnt/gentoo/tmp")
        sh.chmod("+x", "/mnt/gentoo/tmp/sendgentoo_post_chroot.py")
        sh.cp("/etc/resolv.conf", "/mnt/gentoo/etc")


@cli.command()
@click.argument("mount_path")
@click.option(
    "--stdlib",
    required=False,
    type=click.Choice(["glibc", "musl"]),
    default="glibc",
)
@click.option("--boot-device", type=str, required=True)
@click.option("--hostname", type=str, required=True)
@click.option("--march", required=True, type=click.Choice(["native", "nocona"]))
@click.option(
    "--arch",
    is_flag=False,
    required=False,
    type=click.Choice(
        [
            "alpha",
            "amd64",
            "arm",
            "arm64",
            "hppa",
            "ia64",
            "mips",
            "ppc",
            "s390",
            "sh",
            "sparc",
            "x86",
        ]
    ),
    default="amd64",
)
@click.option(
    "--root-filesystem",
    required=False,
    type=click.Choice(["ext4", "zfs", "9p"]),
    default="ext4",
)
@click.option("--newpasswd", type=str, required=True)
@click.option("--skip-to-rsync", is_flag=True)
@click.option("--ip", type=str, required=True)
@click.option("--ip-gateway", type=str, required=True)
@click.option("--pinebook-overlay", type=str, required=False)
@click.option("--vm", required=False, type=click.Choice(["qemu"]))
@click.option("--ipython", is_flag=True)
@click.option("--configure-kernel", is_flag=True)
@click.option(
    "--kernel",
    is_flag=False,
    required=True,
    type=click.Choice(["gentoo-sources", "pinebookpro-manjaro-sources"]),
    default="gentoo-sources",
)
@click_add_options(click_mesa_options)
@click_add_options(click_global_options)
@click.pass_context
def chroot_gentoo(
    ctx,
    mount_path: str,
    stdlib: str,
    boot_device: str,
    hostname: str,
    march: str,
    arch: str,
    root_filesystem: str,
    newpasswd: str,
    ip: str,
    ip_gateway: str,
    vm: str,
    skip_to_rsync: bool,
    mesa_use_enable: list[str],
    mesa_use_disable: list[str],
    pinebook_overlay: bool,
    kernel: str,
    configure_kernel: bool,
    verbose_inf: bool,
    dict_output: bool,
    ipython: bool,
    verbose: bool = False,
):
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    mount_path = Path(mount_path)
    assert path_is_mounted(
        mount_path,
    )

    if not skip_to_rsync:
        ic("making hbrid mbr")
        ctx.invoke(
            make_hybrid_mbr,
            boot_device=boot_device,
            verbose=verbose,
            verbose_inf=verbose_inf,
            dict_output=dict_output,
        )

        # if [[ "${vm}" == "qemu" ]];
        # then
        #    mount --bind "${destination}"{,-chroot} || { echo "${destination} ${destination}-chroot" ; exit 1 ; }
        # fi

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("net"),
            line=f'config_eth0="{ip}/24"\n',
            unique=True,
        )

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("net"),
            line=f'routes_eth0="default via {ip_gateway}"\n',
            unique=True,
        )

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("hostname"),
            line=f'hostname="{hostname}"\n',
            unique=True,
        )

    mount_for_chroot(ctx=ctx, mount_path=mount_path)

    if Path("/etc/portage/proxy.conf").exists():
        sh.cp(
            "/etc/portage/proxy.conf",
            mount_path / Path("etc") / Path("portage") / Path("proxy.conf"),
        )

        write_line_to_file(
            path=mount_path / Path("etc") / Path("portage") / Path("make.conf"),
            line="source /etc/portage/proxy.conf\n",
            unique=True,
        )

    sh.cp(
        "-ar",
        "/home/sysskel/etc/portage/patches",
        mount_path / Path("etc") / Path("portage"),
    )

    write_line_to_file(
        path=mount_path / Path("etc") / Path("hosts"),
        line=f"127.0.0.1\tlocalhost\t{hostname}\n",
        unique=True,
    )

    mesa_use = []
    for flag in mesa_use_enable:
        mesa_use.append(flag)
    for flag in mesa_use_disable:
        mesa_use.append("-" + flag)
    mesa_use = " ".join(mesa_use)
    mesa_use = "media-libs/mesa" + " " + mesa_use

    write_line_to_file(
        path=mount_path
        / Path("etc")
        / Path("portage")
        / Path("package.use")
        / Path("mesa"),
        line=mesa_use + "\n",
        unique=True,
    )

    os.system("/etc/init.d/tinyproxy start")

    sh.emerge("app-misc/tmux", "--fetchonly")

    sh.cp(
        "/usr/bin/ischroot", mount_path / Path("usr") / Path("bin") / Path("ischroot")
    )  # bug for cross compile

    ic("Entering chroot")

    chroot_binary = "chroot"
    if arch != "amd64":
        chroot_binary = "fchroot"

    # old:
    # chroot_command = [
    #     "env",
    #     "-i",
    #     "HOME=/root",
    #     "TERM=$TERM",
    #     chroot_binary,
    #     Path(mount_path).as_posix(),
    #     "/bin/bash",
    #     "-l",
    #     "-c",
    #     "su",
    #     "--login",
    #     "--command",
    # ]
    #
    chroot_command = [
        "env",
        "-i",
        "HOME=/root",
        "TERM=$TERM",
        chroot_binary,
        Path(mount_path).as_posix(),
        "/bin/bash",
        "-l",
        "-c",
    ]

    # new:
    # env -i HOME=/root TERM=$TERM chroot /mnt/gentoo /bin/bash -l -c "/tmp/sendgentoo_post_chroot.py --stdlib glibc --boot-device /dev/sda --march native --newpasswd neww0rld --kernel gentoo-sources ; /bin/bash -l"
    # env -i HOME=/root TERM=$TERM chroot /mnt/gentoo /bin/bash -l -c "/tmp/sendgentoo_post_chroot.py --stdlib glibc --boot-device /dev/sda --march native --newpasswd neww0rld --kernel gentoo-sources ; /bin/bash -l"

    # c_cmd = '-c "/home/cfg/_myapps/sendgentoo-post-chroot/sendgentoo_post_chroot/sendgentoo_post_chroot.py --stdlib {stdlib} --boot-device {boot_device} --march {march} --root-filesystem {root_filesystem} --newpasswd {newpasswd} {pinebook_overlay} --kernel {kernel}"'
    c_cmd = '"/tmp/sendgentoo_post_chroot.py --stdlib {stdlib} --boot-device {boot_device} --march {march} --newpasswd {newpasswd} {pinebook_overlay} --kernel {kernel} {configure_kernel}"'
    c_cmd = c_cmd.format(
        stdlib=stdlib,
        boot_device=boot_device,
        march=march,
        newpasswd=newpasswd,
        pinebook_overlay=("--pinebook-overlay" if pinebook_overlay else ""),
        configure_kernel=("--configure-kernel" if configure_kernel else ""),
        kernel=kernel,
    )
    chroot_command.append(c_cmd)
    run_command(
        " ".join(chroot_command),
        verbose=True,
        ask=False,
        system=True,
    )
    ic("chroot_gentoo.py complete!")


@cli.command()
@click.argument("mount_path")
@click.option(
    "--arch",
    is_flag=False,
    required=False,
    type=click.Choice(
        [
            "alpha",
            "amd64",
            "arm",
            "arm64",
            "hppa",
            "ia64",
            "mips",
            "ppc",
            "s390",
            "sh",
            "sparc",
            "x86",
        ]
    ),
    default="amd64",
)
@click.option("--boot-device", type=str, required=True)
@click.option(
    "--root-filesystem",
    required=False,
    type=click.Choice(["ext4", "zfs", "9p"]),
    default="ext4",
)
@click_add_options(click_global_options)
@click.pass_context
def chroot_gentoo_existing(
    ctx,
    mount_path: str,
    arch: str,
    boot_device: str,
    root_filesystem: str,
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

    mount_path = Path(mount_path)
    assert path_is_mounted(mount_path)

    mount_for_chroot(ctx=ctx, mount_path=mount_path)

    icp("Entering chroot")

    chroot_binary = "chroot"
    if arch != "amd64":
        chroot_binary = "fchroot"

    chroot_command = [
        "env",
        "-i",
        "HOME=/root",
        "TERM=$TERM",
        chroot_binary,
        Path(mount_path).as_posix(),
        "/bin/bash",
        "-l",
        "-c",
        "su",
        "--login",
    ]
    run_command(
        " ".join(chroot_command),
        verbose=True,
        ask=False,
        system=True,
    )
