#!/usr/bin/env python3

import os
import shlex
import sys
from importlib import resources
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

import click
import hs
from asserttool import am_root
from asserttool import ic
from asserttool import icp
from boottool import make_hybrid_mbr
from click_auto_help import AHGroup
from clicktool import click_add_options
from clicktool import click_global_options
from clicktool import tvicgvd
from clicktool.mesa import click_mesa_options
from filetool import append_line_to_file
from globalverbose import gvd
from mounttool import mount_something
from mounttool import path_is_mounted

signal(SIGPIPE, SIG_DFL)

_cp = hs.Command("cp")


def mount_for_chroot(*, ctx: click.Context, mount_path: Path) -> None:
    mount_something(
        mountpoint=mount_path / "proc",
        mount_type="proc",
        source=None,
        slave=False,
    )
    mount_something(
        mountpoint=mount_path / "sys",
        mount_type="rbind",
        slave=True,
        source=Path("/sys"),
    )
    mount_something(
        mountpoint=mount_path / "dev",
        mount_type="rbind",
        slave=True,
        source=Path("/dev"),
    )
    mount_something(
        mountpoint=mount_path / "run",
        mount_type="bind",
        slave=True,
        source=Path("/run"),
    )

    os.makedirs(mount_path / "home" / "cfg", exist_ok=True)
    os.makedirs(mount_path / "usr" / "local" / "portage", exist_ok=True)

    # make sure /var/tmp/portage exists on the host
    hs.Command("emerge")("eprint", _out=sys.stdout, _err=sys.stderr)

    _var_tmp_portage = mount_path / "var" / "tmp" / "portage"
    os.makedirs(_var_tmp_portage, exist_ok=True)
    hs.Command("chown")("portage:portage", _var_tmp_portage.as_posix())

    mount_something(
        mountpoint=_var_tmp_portage,
        mount_type="rbind",
        slave=False,
        source=Path("/var/tmp/portage"),
    )

    _gentoo_repo = mount_path / "var" / "db" / "repos" / "gentoo"
    _gentoo_repo.mkdir(exist_ok=True)
    mount_something(
        mountpoint=_gentoo_repo,
        mount_type="rbind",
        slave=False,
        source=Path("/var/db/repos/gentoo"),
    )

    ctx.invoke(
        rsync_cfg,
        mount_path=mount_path,
    )


@click.group(no_args_is_help=True, cls=AHGroup)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx: click.Context,
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


@cli.command()
@click.argument(
    "mount_path",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        allow_dash=False,
        path_type=Path,
    ),
)
@click_add_options(click_global_options)
@click.pass_context
def rsync_cfg(
    ctx: click.Context,
    mount_path: Path,
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

    am_root()

    hs.Command("rsync")(
        "--exclude=_priv",
        "--exclude=_myapps/gentoo",
        "--exclude=virt/iso",
        "--one-file-system",
        "--delete",
        "--perms",
        "--executability",
        "--human-readable",
        "--recursive",
        "--links",
        "--times",
        "/home/cfg",
        f"{mount_path.as_posix()}/home/",
        _out=sys.stdout,
        _err=sys.stderr,
    )

    with resources.as_file(resources.files("sendgentoo_chroot")) as _pkg_dir:
        _post_chroot_script = _pkg_dir / "sendgentoo_post_chroot.py"
        icp(_post_chroot_script)
        _cp(_post_chroot_script.as_posix(), (mount_path / "tmp").as_posix())
        hs.Command("chmod")(
            "+x", (mount_path / "tmp" / "sendgentoo_post_chroot.py").as_posix()
        )
        _cp("/etc/resolv.conf", (mount_path / "etc").as_posix())


@cli.command()
@click.argument(
    "mount_path",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        allow_dash=False,
        path_type=Path,
    ),
)
@click.option(
    "--stdlib",
    required=False,
    type=click.Choice(["glibc", "musl"]),
    default="glibc",
)
@click.option(
    "--boot-device",
    type=click.Path(
        exists=True,
        dir_okay=False,
        file_okay=True,
        allow_dash=False,
        path_type=Path,
    ),
    required=True,
)
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
@click.option("--skip-to-rsync", is_flag=True)
@click.option("--ip", type=str, required=True)
@click.option("--ip-gateway", type=str, required=True)
@click.option("--pinebook-overlay", is_flag=True)
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
    ctx: click.Context,
    mount_path: Path,
    stdlib: str,
    boot_device: Path,
    hostname: str,
    march: str,
    arch: str,
    root_filesystem: str,
    ip: str,
    ip_gateway: str,
    vm: None | str,
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
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    mount_path = Path(mount_path)
    assert path_is_mounted(mount_path)

    if not skip_to_rsync:
        ic("making hybrid mbr")
        ctx.invoke(
            make_hybrid_mbr,
            boot_device=boot_device,
            verbose=verbose,
            verbose_inf=verbose_inf,
            dict_output=dict_output,
        )

        append_line_to_file(
            path=mount_path / "etc" / "conf.d" / "net",
            line=f'config_eth0="{ip}/24"',
            unique=True,
        )
        append_line_to_file(
            path=mount_path / "etc" / "conf.d" / "net",
            line=f'routes_eth0="default via {ip_gateway}"',
            unique=True,
        )
        append_line_to_file(
            path=mount_path / "etc" / "conf.d" / "hostname",
            line=f'hostname="{hostname}"',
            unique=True,
        )

    mount_for_chroot(ctx=ctx, mount_path=mount_path)

    if Path("/etc/portage/proxy.conf").exists():
        _cp(
            "/etc/portage/proxy.conf",
            (mount_path / "etc" / "portage" / "proxy.conf").as_posix(),
        )
        append_line_to_file(
            path=mount_path / "etc" / "portage" / "make.conf",
            line="source /etc/portage/proxy.conf",
            unique=True,
        )
        hs.Command("/etc/init.d/tinyproxy")("start", _out=sys.stdout, _err=sys.stderr)

    _cp(
        "-ar",
        "/home/sysskel/etc/portage/patches",
        (mount_path / "etc" / "portage").as_posix(),
    )

    append_line_to_file(
        path=mount_path / "etc" / "hosts",
        line=f"127.0.0.1\tlocalhost\t{hostname}",
        unique=True,
    )

    mesa_use = " ".join(
        [*mesa_use_enable, *("-" + flag for flag in mesa_use_disable)]
    )
    append_line_to_file(
        path=mount_path / "etc" / "portage" / "package.use" / "mesa",
        line=f"media-libs/mesa {mesa_use}",
        unique=True,
    )

    hs.Command("emerge")(
        "app-misc/tmux", "--fetchonly", _out=sys.stdout, _err=sys.stderr
    )

    # cross-compile bug: chroot needs the host ischroot
    _cp("/usr/bin/ischroot", (mount_path / "usr" / "bin" / "ischroot").as_posix())

    ic("Entering chroot")

    chroot_binary = "chroot"
    if arch != "amd64":
        chroot_binary = "fchroot"

    post_chroot_args = [
        "/tmp/sendgentoo_post_chroot.py",
        "--stdlib",
        stdlib,
        "--boot-device",
        boot_device.as_posix(),
        "--march",
        march,
        "--kernel",
        kernel,
    ]
    if pinebook_overlay:
        post_chroot_args.append("--pinebook-overlay")
    if configure_kernel:
        post_chroot_args.append("--configure-kernel")
    c_cmd = " ".join(shlex.quote(_arg) for _arg in post_chroot_args)

    hs.Command("env")(
        "-i",
        "HOME=/root",
        f"TERM={os.environ['TERM']}",
        chroot_binary,
        mount_path.as_posix(),
        "/bin/bash",
        "-l",
        "-c",
        c_cmd,
        _fg=True,
    )
    ic("chroot_gentoo complete!")


@cli.command()
@click.argument(
    "mount_path",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        allow_dash=False,
        path_type=Path,
    ),
)
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
    "--boot-device",
    type=click.Path(
        exists=True,
        dir_okay=False,
        file_okay=True,
        allow_dash=False,
        path_type=Path,
    ),
    required=True,
)
@click.option(
    "--root-filesystem",
    required=False,
    type=click.Choice(["ext4", "zfs", "9p"]),
    default="ext4",
)
@click_add_options(click_global_options)
@click.pass_context
def chroot_gentoo_existing(
    ctx: click.Context,
    mount_path: Path,
    arch: str,
    boot_device: Path,
    root_filesystem: str,
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

    mount_path = Path(mount_path)
    assert path_is_mounted(mount_path)

    mount_for_chroot(ctx=ctx, mount_path=mount_path)

    icp("Entering chroot")

    chroot_binary = "chroot"
    if arch != "amd64":
        chroot_binary = "fchroot"

    hs.Command("env")(
        "-i",
        "HOME=/root",
        f"TERM={os.environ['TERM']}",
        chroot_binary,
        mount_path.as_posix(),
        "/bin/bash",
        "-l",
        "-c",
        "su",
        "--login",
        _fg=True,
    )
