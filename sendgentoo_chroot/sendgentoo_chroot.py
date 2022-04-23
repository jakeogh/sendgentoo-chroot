#!/usr/bin/env python3
# -*- coding: utf8 -*-

# pylint: disable=C0111  # docstrings are always outdated and wrong
# pylint: disable=C0114  #      Missing module docstring (missing-module-docstring)
# pylint: disable=W0511  # todo is encouraged
# pylint: disable=C0301  # line too long
# pylint: disable=R0902  # too many instance attributes
# pylint: disable=C0302  # too many lines in module
# pylint: disable=C0103  # single letter var names, func name too descriptive
# pylint: disable=R0911  # too many return statements
# pylint: disable=R0912  # too many branches
# pylint: disable=R0915  # too many statements
# pylint: disable=R0913  # too many arguments
# pylint: disable=R1702  # too many nested blocks
# pylint: disable=R0914  # too many local variables
# pylint: disable=R0903  # too few public methods
# pylint: disable=E1101  # no member for base
# pylint: disable=W0201  # attribute defined outside __init__
# pylint: disable=R0916  # Too many boolean expressions in if statement
# pylint: disable=C0305  # Trailing newlines editor should fix automatically, pointless warning


import os
import sys
# import time
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal
# from typing import ByteString
# from typing import Generator
# from typing import Iterable
# from typing import List
# from typing import Optional
# from typing import Sequence
# from typing import Tuple
from typing import Union

import click
import sh
from asserttool import ic
from asserttool import root_user
from boottool import make_hybrid_mbr
from clicktool import click_add_options
from clicktool import click_global_options
from clicktool import tv
from clicktool.mesa import click_mesa_options
# from eprint import eprint
from mounttool import mount_something
from mounttool import path_is_mounted
# from pathtool import path_is_block_special
from pathtool import write_line_to_file
# from retry_on_exception import retry_on_exception
from run_command import run_command
from with_chdir import chdir

signal(SIGPIPE, SIG_DFL)


@click.group(no_args_is_help=True)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):
    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )


@cli.command()
@click.argument("mount_path")
@click_add_options(click_global_options)
@click.pass_context
def rsync_cfg(
    ctx,
    mount_path: str,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):
    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    if not root_user():
        ic("You must be root.")
        sys.exit(1)

    with chdir(
        "/home/",
        verbose=verbose,
    ):
        #    "--verbose",
        #    "--progress",
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


@cli.command()
@click.argument("mount_path")
@click.option(
    "--stdlib", required=False, type=click.Choice(["glibc", "musl"]), default="glibc"
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
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
    ipython: bool,
):
    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    mount_path = Path(mount_path)
    assert path_is_mounted(
        mount_path,
        verbose=verbose,
    )

    if not skip_to_rsync:
        ic("making hbrid mbr")
        ctx.invoke(
            make_hybrid_mbr,
            boot_device=boot_device,
            verbose=verbose,
            verbose_inf=verbose_inf,
            dict_input=dict_input,
        )

        # if [[ "${vm}" == "qemu" ]];
        # then
        #    mount --bind "${destination}"{,-chroot} || { echo "${destination} ${destination}-chroot" ; exit 1 ; }
        # fi

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("net"),
            line=f'config_eth0="{ip}/24"\n',
            unique=True,
            verbose=verbose,
        )

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("net"),
            line=f'routes_eth0="default via {ip_gateway}"\n',
            unique=True,
            verbose=verbose,
        )

        write_line_to_file(
            path=mount_path / Path("etc") / Path("conf.d") / Path("hostname"),
            line=f'hostname="{hostname}"\n',
            unique=True,
            verbose=verbose,
        )

    mount_something(
        mountpoint=mount_path / Path("proc"),
        mount_type="proc",
        source=None,
        slave=False,
        verbose=verbose,
    )
    mount_something(
        mountpoint=mount_path / Path("sys"),
        mount_type="rbind",
        slave=True,
        source=Path("/sys"),
        verbose=verbose,
    )
    mount_something(
        mountpoint=mount_path / Path("dev"),
        mount_type="rbind",
        slave=True,
        source=Path("/dev"),
        verbose=verbose,
    )
    mount_something(
        mountpoint=mount_path / Path("run"),
        mount_type="bind",
        slave=True,
        source=Path("/run"),
        verbose=verbose,
    )

    os.makedirs(mount_path / Path("home") / Path("cfg"), exist_ok=True)

    os.makedirs(
        mount_path / Path("usr") / Path("local") / Path("portage"), exist_ok=True
    )

    _var_tmp_portage = mount_path / Path("var") / Path("tmp") / Path("portage")
    os.makedirs(_var_tmp_portage, exist_ok=True)
    sh.chown("portage:portage", _var_tmp_portage)
    mount_something(
        mountpoint=_var_tmp_portage,
        mount_type="rbind",
        slave=False,
        source=Path("/var/tmp/portage"),
        verbose=verbose,
    )
    del _var_tmp_portage

    ctx.invoke(
        rsync_cfg,
        mount_path=mount_path,
        verbose=verbose,
    )

    _repos_conf = mount_path / Path("etc") / Path("portage") / Path("repos.conf")
    os.makedirs(_repos_conf, exist_ok=True)
    sh.cp("/home/cfg/sysskel/etc/portage/repos.conf/gentoo.conf", _repos_conf)
    del _repos_conf

    _gentoo_repo = (
        mount_path / Path("var") / Path("db") / Path("repos") / Path("gentoo")
    )
    os.makedirs(_gentoo_repo, exist_ok=True)
    mount_something(
        mountpoint=_gentoo_repo,
        mount_type="rbind",
        slave=False,
        source=Path("/var/db/repos/gentoo"),
        verbose=verbose,
    )
    del _gentoo_repo

    sh.cp(
        "/etc/portage/proxy.conf",
        mount_path / Path("etc") / Path("portage") / Path("proxy.conf"),
    )

    write_line_to_file(
        path=mount_path / Path("etc") / Path("portage") / Path("make.conf"),
        line="source /etc/portage/proxy.conf\n",
        unique=True,
        verbose=verbose,
    )

    write_line_to_file(
        path=mount_path / Path("etc") / Path("hosts"),
        line=f"127.0.0.1\tlocalhost\t{hostname}\n",
        unique=True,
        verbose=verbose,
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
        verbose=verbose,
    )

    sh.cp(
        "/usr/bin/ischroot", mount_path / Path("usr") / Path("bin") / Path("ischroot")
    )  # bug for cross compile

    ic("Entering chroot")

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
        "-",
    ]
    c_cmd = '-c "/home/cfg/_myapps/sendgentoo-post-chroot/sendgentoo_post_chroot/sendgentoo_post_chroot.py --stdlib {stdlib} --boot-device {boot_device} --march {march} --root-filesystem {root_filesystem} --newpasswd {newpasswd} {pinebook_overlay} --kernel {kernel}"'
    c_cmd = c_cmd.format(
        stdlib=stdlib,
        boot_device=boot_device,
        march=march,
        root_filesystem=root_filesystem,
        newpasswd=newpasswd,
        pinebook_overlay=("--pinebook-overlay" if pinebook_overlay else ""),
        kernel=kernel,
    )
    chroot_command.append(c_cmd)
    run_command(" ".join(chroot_command), verbose=True, ask=True, system=True)
    ic("chroot_gentoo.py complete!")
