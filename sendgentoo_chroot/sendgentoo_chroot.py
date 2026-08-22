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
    # /run must be private, never a bind of the host's. The chroot shares the
    # host PID namespace, so a shared /run hands every openrc invocation in
    # the chroot the host's service state and pidfiles: openssh's
    # pkg_postinst runs rc-service --ifstarted sshd restart when replacing a
    # pre-split version (bug 709748), which read the netboot sshd as started
    # through the shared /run, killed it through the shared pidfile, and
    # bound the chroot's stock-config sshd on the freed port -- every
    # install, minutes into the world update. A fresh tmpfs leaves the
    # chroot's openrc seeing no started services, so --ifstarted is a no-op
    # and nothing can act across the boundary in either direction.
    mount_something(
        mountpoint=mount_path / "run",
        mount_type="tmpfs",
        slave=False,
        source=None,
    )

    os.makedirs(mount_path / "usr" / "local" / "portage", exist_ok=True)

    # Build on the target's disk, not in the netboot environment. This used to
    # be bind mounted from the host, whose root is a tmpfs overlay over the
    # squashfs and therefore capped at half of RAM: every package compiled
    # into memory and a large one ran the machine out of space. The target's
    # own filesystem has the whole disk.
    _var_tmp_portage = mount_path / "var" / "tmp" / "portage"
    os.makedirs(_var_tmp_portage, exist_ok=True)
    hs.Command("chown")("portage:portage", _var_tmp_portage.as_posix())

    # Every repository this environment has, not just gentoo: the target
    # cannot reach github or a rsync mirror, so anything it is not given here
    # it cannot obtain at all. auto-sync is off for the same reason -- these
    # are the server's trees and syncing them is the server's job.
    _repos_conf = mount_path / "etc" / "portage" / "repos.conf"
    _repos_conf.mkdir(parents=True, exist_ok=True)
    _entries = []
    for _repo in str(hs.Command("portageq")("get_repos", "/")).split():
        _path = Path(
            str(hs.Command("portageq")("get_repo_path", "/", _repo)).strip()
        )
        assert _path.is_dir(), f"repository {_repo} is not at {_path.as_posix()}"
        _target = mount_path / _path.relative_to("/")
        _target.mkdir(parents=True, exist_ok=True)
        mount_something(
            mountpoint=_target,
            mount_type="rbind",
            slave=False,
            source=_path,
        )
        _entries.append(
            f"[{_repo}]\nlocation = {_path.as_posix()}\nauto-sync = no\n"
        )
    (_repos_conf / "sendgentoo.conf").write_text(
        "# bound from the deployment environment; the target syncs nothing\n\n"
        + "\n".join(_entries),
        encoding="utf8",
    )
    print(f"repos bound into {mount_path.as_posix()}: {len(_entries)}", file=sys.stderr)

    ctx.invoke(
        install_post_chroot,
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
def install_post_chroot(
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
@click.option("--root-password", required=False, type=str, default=None)
@click.option("--distfiles-url", required=True, type=str)
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
    root_password: None | str,
    distfiles_url: str,
    boot_device: Path,
    hostname: str,
    arch: str,
    root_filesystem: str,
    ip: str,
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

    _var_cache_distfiles = mount_path / "var" / "cache" / "distfiles"
    os.makedirs(_var_cache_distfiles, exist_ok=True)
    hs.Command("chown")("portage:portage", _var_cache_distfiles.as_posix())
    append_line_to_file(
        path=mount_path / "etc" / "portage" / "make.conf",
        line=f'GENTOO_MIRRORS="{distfiles_url}"',
        unique=True,
    )

    # the same rewrite this environment uses: it names the deployment server,
    # which is the only host the target can reach, so live ebuilds resolve
    _cp("/etc/gitconfig", (mount_path / "etc" / "gitconfig").as_posix())

    # The overlay's live ebuilds carry no KEYWORDS, so without this every one
    # of them sends portage into autounmask, which writes config and exits
    # non-zero rather than building. The deployment environment accepts them
    # by the same rule; the target has to state it too.
    _keywords = mount_path / "etc" / "portage" / "package.accept_keywords"
    assert not _keywords.is_file(), (
        f"{_keywords.as_posix()} is a file; this expects the directory form"
    )
    _keywords.mkdir(parents=True, exist_ok=True)
    (_keywords / "sendgentoo").write_text(
        "*/*::jakeogh **\n", encoding="utf8"
    )

    # dev-python/ptyprocess requires flit-core below 4 and no newer revision
    # exists, so a tree carrying flit-core 4 satisfies neither side. Stated
    # here as well as in the image because the target resolves its own world.
    _mask = mount_path / "etc" / "portage" / "package.mask"
    assert not _mask.is_file(), (
        f"{_mask.as_posix()} is a file; this expects the directory form"
    )
    _mask.mkdir(parents=True, exist_ok=True)
    (_mask / "sendgentoo").write_text(">=dev-python/flit-core-4\n", encoding="utf8")

    _use = mount_path / "etc" / "portage" / "package.use"
    assert not _use.is_file(), (
        f"{_use.as_posix()} is a file; this expects the directory form"
    )
    _use.mkdir(parents=True, exist_ok=True)
    (_use / "sendgentoo").write_text(
        # Two optional features pull rust for no benefit here:
        # charset-normalizer's native-extensions is a mypyc speedup that pulls
        # mypy, ast-serialize, maturin and rust, and git's rust flag pulls two
        # further rust slots. Neither is needed to install a system, and each
        # rust is a multi hour build.
        "dev-python/charset-normalizer -native-extensions\n"
        "dev-vcs/git -rust\n",
        encoding="utf8",
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
        "--kernel",
        kernel,
    ]
    if root_password:
        post_chroot_args += ["--root-password", root_password]
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
