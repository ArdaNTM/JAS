"""OSWorld-V2.1 Python 3.12 *subprocess* worker, isolated from AURA 3.13.

Only stdlib imports at startup; OSWorld and Docker SDK load *inside this
separate interpreter*. All commands are JSON-lines over inherited private
stdio; the worker has no HTTP, sockets or unauthenticated listener. User GUI
actions still require the AURA MCP Gateway's consumed Owner approval *before*
they are sent here. Malformed/extraneous commands fail closed.

The official DockerProvider is patched in THIS PROCESS ONLY, after pinned
upstream Git commit verification, to enforce the exact internal network and
loopback host port binds before creating a VM. This never modifies the cloned
OSWorld source files nor the immutable AURA Kernel.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

EXPECTED_COMMIT = "3d778a3c9a34a079316f70df023b166700445792"
RELEASE = "osworld-v2.1"
NETWORK = "aura-osworld-v21-lab"
IMAGE = "happysixd/osworld-docker@sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
PORTS = (5000, 8006, 8080, 9222)
# Explicit QEMU SLIRP forwarding avoids kernel iptables NAT on Docker Desktop.
# 8006 is the container's own web UI, never a forwarded guest listener.
GUEST_NETWORK_MODE = "user"
GUEST_FORWARD_PORTS = "5000,8080,9222"
CONTAINER_ONLY_PORTS = "8006"
# Empty root-owned, memory-bounded log directory: no DAC_OVERRIDE, no host bind.
NGINX_LOG_TMPFS = "rw,nosuid,nodev,noexec,size=16m,mode=0755"
STORAGE_VOLUME_PREFIX = "aura-osworld-v21-storage-"
STORAGE_VOLUME_PURPOSE = "vm-storage"
# The pinned image carries this read-only firmware; copy it to a fresh,
# isolated Docker volume *before* QEMU starts and explicitly set 0644.
# Never chmod a host path, broaden DAC privileges or overlay /storage on RAM.
STORAGE_SEED_SCRIPT = """set -eu
umask 022
test -d /storage
test -f /usr/share/OVMF/edk2-x86_64-code.fd
test ! -e /storage/uefi.rom
test ! -e /storage/uefi.vars
chmod 0755 /storage
cp /usr/share/OVMF/edk2-x86_64-code.fd /storage/uefi.rom
chmod 0644 /storage/uefi.rom
test -r /storage/uefi.rom
test -s /storage/uefi.rom
"""
ALLOWED_KEYS = frozenset({"enter", "esc", "tab", "backspace", "space", "up", "down", "left", "right"})
UUID_ID = re.compile(r"^[0-9a-f]{3}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON = 16384


class WorkerDenied(PermissionError):
    pass


def git_revision(upstream: Path) -> None:
    def git(*cmd: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(upstream), *cmd],
            text=True, timeout=15,
        ).strip()
    if git("rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise WorkerDenied("OSWorld source changed from pinned release")
    if git("describe", "--tags", "--exact-match", "HEAD") != RELEASE:
        raise WorkerDenied("OSWorld tag does not match osworld-v2.1")


def digest_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise WorkerDenied("Missing independently provisioned QCOW2 disk")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_docker_network(client: object) -> str:
    network = client.networks.get(NETWORK)
    network.reload()
    data = network.attrs
    if (data.get("Name") != NETWORK or data.get("Internal") is not True
            or data.get("EnableIPv6") is not False or data.get("Driver") != "bridge"):
        raise WorkerDenied("OSWorld network must be an internal IPv4 bridge")
    network_id = data.get("Id", "")
    if not isinstance(network_id, str) or not DIGEST.fullmatch(network_id):
        raise WorkerDenied("Invalid Docker network ID")
    return network_id


def verify_running_container(container: object, network_id: str) -> None:
    """Reinspect before every action; invalidate approvals after re-networking."""
    container.reload()
    attrs = container.attrs
    host = attrs.get("HostConfig") or {}
    settings = attrs.get("NetworkSettings") or {}
    networks = settings.get("Networks") or {}
    env = (attrs.get("Config") or {}).get("Env")
    if not isinstance(env, list) or not all(isinstance(item, str) for item in env):
        raise WorkerDenied("Missing pinned QEMU network environment")
    for key, expected in (
        ("NETWORK", GUEST_NETWORK_MODE),
        ("USER_PORTS", GUEST_FORWARD_PORTS),
        ("HOST_PORTS", CONTAINER_ONLY_PORTS),
    ):
        if [item[len(key) + 1:] for item in env if item.startswith(key + "=")] != [expected]:
            raise WorkerDenied("Unexpected QEMU network mode or forwarded ports")
    if (attrs.get("State", {}).get("Running") is not True
            or attrs.get("Config", {}).get("Image") != IMAGE
            or host.get("Privileged") is not False
            or host.get("NetworkMode") != NETWORK
            or set(networks) != {NETWORK}
            or networks[NETWORK].get("NetworkID") != network_id):
        raise WorkerDenied("Running VM network or image has changed")
    if (host.get("Tmpfs") or {}) != {"/var/log/nginx": NGINX_LOG_TMPFS}:
        raise WorkerDenied("Nginx logs must use the exact bounded private tmpfs")
    labels = attrs.get("Config", {}).get("Labels") or {}
    run_id = labels.get("aura.osworld.run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise WorkerDenied("Running VM lacks protected run identity")
    storage = STORAGE_VOLUME_PREFIX + run_id
    mounts = attrs.get("Mounts") or []
    if (not isinstance(mounts, list)
            or not all(isinstance(m, dict) for m in mounts)
            or len({m.get("Destination") for m in mounts}) != len(mounts)
            or len(mounts) not in (2, 3)
            or len([m for m in mounts if m.get("Destination") == "/storage"
                    and m.get("Type") == "volume" and m.get("Name") == storage
                    and m.get("RW") is True]) != 1
            or len([m for m in mounts if m.get("Destination") == "/System.qcow2"
                    and m.get("Type") in ("bind", None)
                    and m.get("RW") is False]) != 1
            or any(m.get("Destination") not in (
                "/storage", "/System.qcow2", "/var/log/nginx")
                for m in mounts)
            or any(m.get("Destination") == "/var/log/nginx"
                   and (m.get("Type") != "tmpfs" or m.get("RW") is not True)
                   for m in mounts)):
        raise WorkerDenied("Unapproved VM storage mount")
    devices = host.get("Devices") or []
    keys = {(d.get("PathOnHost"), d.get("PathInContainer"), d.get("CgroupPermissions"))
            for d in devices if isinstance(d, dict)}
    if (len(keys) != len(devices) or
            ("/dev/net/tun", "/dev/net/tun", "rwm") not in keys
            or keys - {
                ("/dev/net/tun", "/dev/net/tun", "rwm"),
                ("/dev/kvm", "/dev/kvm", "rwm"),
            }):
        raise WorkerDenied("Required pinned TUN /dev/net/tun device missing or changed")
    host_ports = host.get("PortBindings") or {}
    if set(host_ports) != {str(p) + "/tcp" for p in PORTS}:
        raise WorkerDenied("Unexpected VM control port")
    for port in PORTS:
        entry = host_ports.get(str(port) + "/tcp")
        if (not isinstance(entry, list) or len(entry) != 1
                or entry[0].get("HostIp") != "127.0.0.1"):
            raise WorkerDenied("Control port escaped localhost")


def secure_docker_patch(
    boot_timeout: int, *, force_no_kvm: bool = False,
    run_id: str = "00000000000000000000000000000000",
) -> None:
    """Strict replacement for the official provider's permissive start method."""
    from desktop_env.providers.docker.provider import DockerProvider, FileLock
    from pathlib import Path as LocalPath

    if not 300 <= boot_timeout <= 1200:
        raise WorkerDenied("Boot timeout outside bounded 300..1200 seconds")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise WorkerDenied("Missing bounded trusted Docker run identity")

    def start_emulator(self, path_to_vm: str, headless: bool, os_type: str) -> None:
        if os_type != "Ubuntu":
            raise WorkerDenied("Only pinned disposable Ubuntu image accepted")
        disk = LocalPath(path_to_vm).resolve(strict=True)
        if disk.is_symlink() or not disk.is_file():
            raise WorkerDenied("Expected external read-only QCOW2 image")
        network_id = verify_docker_network(self.client)
        volume_name = STORAGE_VOLUME_PREFIX + run_id
        # A per-run local named volume permits sparse guest disks without
        # exposing any writable host bind mount or unbounded tmpfs.
        # The init container never joins a network or receives host secrets.
        try:
            volume = self.client.volumes.create(
                name=volume_name,
                driver="local",
                labels={
                    "aura.osworld.run_id": run_id,
                    "aura.osworld.purpose": STORAGE_VOLUME_PURPOSE,
                },
            )
            self._aura_storage_volume = volume
            self.client.containers.run(
                IMAGE, command=[STORAGE_SEED_SCRIPT],
                entrypoint=["/bin/sh", "-ec"], user="0:0",
                network_mode="none",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=32,
                volumes={volume_name: {"bind": "/storage", "mode": "rw"}},
                remove=True, detach=False,
            )
            with FileLock(str(self.lock_file), timeout=20):
                self.vnc_port = self._get_available_port(8006)
                self.server_port = self._get_available_port(5000)
                self.chromium_port = self._get_available_port(9222)
                self.vlc_port = self._get_available_port(8080)
                # No /dev/kvm on Docker Desktop/WSL2 => QEMU software mode.
                devices: list[str] = ["/dev/net/tun:/dev/net/tun:rwm"]
                if not force_no_kvm and os.name != "nt" and os.path.exists("/dev/kvm"):
                    devices.append("/dev/kvm")
                    self.environment["KVM"] = "Y"
                else:
                    self.environment["KVM"] = "N"
                self.container = self.client.containers.run(
                    IMAGE, network=NETWORK,
                    labels={"aura.osworld.run_id": run_id},
                    environment={
                        **self.environment,
                        "AURA_OSWORLD_GOVERNED": "1",
                        "NETWORK": GUEST_NETWORK_MODE,
                        "USER_PORTS": GUEST_FORWARD_PORTS,
                        "HOST_PORTS": CONTAINER_ONLY_PORTS,
                    },
                    # The pinned Nginx startup chowns /var/lib/nginx/body
                    # to www-data (uid 33); CAP_CHOWN is the minimal required
                    # capability. Do not restore Docker defaults or privileged.
                    cap_drop=["ALL"], cap_add=["CHOWN", "NET_ADMIN"],
                    security_opt=["no-new-privileges:true"],
                    pids_limit=512,
                    devices=devices,
                    volumes={
                        str(disk): {"bind": "/System.qcow2", "mode": "ro"},
                        volume_name: {"bind": "/storage", "mode": "rw"},
                    },
                    # The pinned Nginx image's pre-existing error.log is not
                    # writable without broad DAC permissions. Overlay only its
                    # log DIRECTORY with an empty, root-owned, size-bounded tmpfs.
                    # No host bind, entrypoint override, or new Linux capability.
                    tmpfs={"/var/log/nginx": NGINX_LOG_TMPFS},
                    ports={
                        8006: ("127.0.0.1", self.vnc_port),
                        5000: ("127.0.0.1", self.server_port),
                        9222: ("127.0.0.1", self.chromium_port),
                        8080: ("127.0.0.1", self.vlc_port),
                    },
                    detach=True,
                )
            verify_running_container(self.container, network_id)
            self._wait_for_vm_ready(timeout=boot_timeout)
            verify_running_container(self.container, network_id)
        except BaseException:
            if self.container is not None:
                try:
                    self.container.stop(timeout=3)
                    self.container.remove(force=True)
                except Exception:
                    pass
                self.container = None
            # Never use force=True: remove only the fresh volume we created,
            # after the container has been removed.
            volume = getattr(self, "_aura_storage_volume", None)
            if volume is not None:
                try:
                    volume.remove(force=False)
                except Exception:
                    pass
                self._aura_storage_volume = None
            raise

    original_stop_emulator = DockerProvider.stop_emulator

    def stop_emulator(self, *args, **kwargs):
        try:
            return original_stop_emulator(self, *args, **kwargs)
        finally:
            volume = getattr(self, "_aura_storage_volume", None)
            if volume is not None:
                try:
                    volume.remove(force=False)
                except Exception:
                    pass
                self._aura_storage_volume = None

    DockerProvider.start_emulator = start_emulator
    DockerProvider.stop_emulator = stop_emulator


def _action(value: object) -> str:
    """Independent worker validation; never execute caller-supplied source."""
    if not isinstance(value, dict) or set(value) - {"action", "x", "y", "text", "key"}:
        raise WorkerDenied("Invalid guest action envelope")
    kind = value.get("action")
    if kind == "click":
        if (set(value) != {"action", "x", "y"}
                or type(value["x"]) is not int or type(value["y"]) is not int
                or not 0 <= value["x"] < 1920 or not 0 <= value["y"] < 1080):
            raise WorkerDenied("Invalid click coordinates")
        return f"pyautogui.click({value['x']}, {value['y']})"
    if kind == "type":
        text = value.get("text")
        if (set(value) != {"action", "text"} or not isinstance(text, str)
                or not 1 <= len(text) <= 500
                or any(ord(x) < 32 or ord(x) == 127 for x in text)):
            raise WorkerDenied("Untrusted typed text")
        return f"pyautogui.write({json.dumps(text, ensure_ascii=True)}, interval=0.01)"
    if kind == "key":
        key = value.get("key")
        if set(value) != {"action", "key"} or not isinstance(key, str) or key not in ALLOWED_KEYS:
            raise WorkerDenied("Untrusted keyboard command")
        return f"pyautogui.press({json.dumps(key)})"
    if kind in {"done", "wait"} and set(value) == {"action"}:
        return kind.upper()
    raise WorkerDenied("Unsupported VM action")


def load_official_task(upstream: Path, task_id: str, sha256: str) -> object:
    """Only an explicit operator-approved, hash-bound official task class."""
    if not isinstance(task_id, str) or not UUID_ID.fullmatch(task_id):
        raise WorkerDenied("Official V2 task ID must have three numeric digits")
    if not isinstance(sha256, str) or not DIGEST.fullmatch(sha256):
        raise WorkerDenied("Operator must approve exact task SHA-256")
    task_path = upstream / "evaluation_examples" / "task_class" / f"task_{task_id}.py"
    task_path = task_path.resolve(strict=True)
    if not task_path.is_relative_to(upstream.resolve(strict=True)) or task_path.is_symlink():
        raise WorkerDenied("Official task cannot escape pinned checkout")
    if task_path.stat().st_size > 500_000 or digest_file(task_path) != sha256:
        raise WorkerDenied("Official task source differs from approved hash")
    spec = importlib.util.spec_from_file_location("osworld_v2_task_" + task_id, task_path)
    if spec is None or spec.loader is None:
        raise WorkerDenied("Pinned official task module unavailable")
    from desktop_env.task_base import BaseTask
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, "TASK_CLASS", None)
    if not isinstance(cls, type) or not issubclass(cls, BaseTask):
        raise WorkerDenied("Official V2 task module has no BaseTask TASK_CLASS")
    task = cls()
    if str(task.get("id")) != task_id:
        raise WorkerDenied("Task class ID did not match operator-approved path")
    return task


def _observation(obs: object) -> dict[str, object]:
    if not isinstance(obs, dict):
        raise WorkerDenied("Unrecognized upstream observation")
    return {
        "accessibility_tree": str(obs.get("accessibility_tree") or "")[:12000],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--vm-image", type=Path, required=True)
    p.add_argument("--assets", type=Path)
    p.add_argument("--website-suffix")
    p.add_argument("--boot-timeout", type=int, default=900)
    p.add_argument("--no-kvm", action="store_true")
    p.add_argument("--run-id", required=True)
    args = p.parse_args(argv)
    wire = sys.stdout
    env = None
    try:
        if sys.version_info[:2] != (3, 12):
            raise WorkerDenied("Isolated OSWorld worker MUST run under Python 3.12")
        upstream = args.upstream.resolve(strict=True)
        git_revision(upstream)
        vm_image = args.vm_image.resolve(strict=True)
        if (not vm_image.is_relative_to(upstream / "docker_vm_data")
                or vm_image.name != "osworld-v2-ubuntu-x86.qcow2"):
            raise WorkerDenied("VM disk must be the official OSWorld Ubuntu QCOW2")
        vm_hash = digest_file(vm_image)
        if args.assets is not None:
            assets = args.assets.resolve(strict=True)
            if not assets.is_dir() or not any(assets.iterdir()):
                raise WorkerDenied("Operator-provisioned asset directory empty")
            os.environ["OSWORLD_FILE_BASE_URL"] = str(assets)
        os.environ["OSWORLD_BENCHMARK_RELEASE"] = RELEASE
        if args.website_suffix is not None:
            if (not args.website_suffix or len(args.website_suffix) > 128
                    or any(x in args.website_suffix for x in " /:@\\")
                    or not re.fullmatch(r"[A-Za-z0-9.-]+", args.website_suffix)):
                raise WorkerDenied("Invalid externally hosted test domain suffix")
            os.environ["WEBSITE_HOST_SUFFIX"] = args.website_suffix
        os.chdir(upstream)
        sys.path.insert(0, str(upstream))
        with contextlib.redirect_stdout(sys.stderr):
            secure_docker_patch(
                args.boot_timeout, force_no_kvm=args.no_kvm,
                run_id=args.run_id,
            )
            from desktop_env.desktop_env import DesktopEnv
            env = DesktopEnv(
                provider_name="docker", os_type="Ubuntu",
                path_to_vm=str(vm_image), headless=True,
                action_space="pyautogui", screen_size=(1920, 1080),
                require_a11y_tree=True,
            )
        container = env.provider.container
        net_id = verify_docker_network(env.provider.client)
        verify_running_container(container, net_id)
        boot = {
            "container_id": container.id,
            "network_id": net_id,
            "vm_sha256": vm_hash,
            "image": IMAGE,
        }
        wire.write(json.dumps({"ok": True, "boot": boot,
                               "kvm_mode": env.provider.environment.get("KVM")},
                              separators=(",", ":")) + "\n")
        wire.flush()
        while True:
            line = sys.stdin.readline(MAX_JSON + 1)
            if not line:
                break
            if len(line) > MAX_JSON or not line.endswith("\n"):
                raise WorkerDenied("Oversized or unterminated worker request")
            try:
                req = json.loads(line)
                if not isinstance(req, dict) or "op" not in req:
                    raise WorkerDenied("Malformed worker request")
                op = req["op"]
                if op == "close" and set(req) == {"op"}:
                    wire.write('{"ok":true}\n')
                    wire.flush()
                    break
                if op == "reset" and set(req) == {"op", "task_id", "task_sha256"}:
                    verify_running_container(container, net_id)
                    with contextlib.redirect_stdout(sys.stderr):
                        task = load_official_task(upstream, req["task_id"], req["task_sha256"])
                        obs = env.reset(task)
                    reply = {"ok": True, "observation": _observation(obs),
                             "instruction": str(task.get("instruction", ""))[:2000]}
                elif op == "step" and set(req) == {"op", "action"}:
                    verify_running_container(container, net_id)
                    command = _action(req["action"])
                    with contextlib.redirect_stdout(sys.stderr):
                        obs, _, done, _ = env.step(command, pause=0)
                    reply = {"ok": True, "observation": _observation(obs), "done": bool(done)}
                elif op == "evaluate" and set(req) == {"op"}:
                    verify_running_container(container, net_id)
                    with contextlib.redirect_stdout(sys.stderr):
                        result = env.evaluate()  # EXACT official OSWorld-V2.1 signature
                    value = result.get("score") if isinstance(result, dict) else result
                    if (type(value) not in (int, float) or not math.isfinite(value)
                            or not 0 <= value <= 1):
                        raise WorkerDenied("Official evaluator returned no valid score")
                    reply = {"ok": True, "score": float(value)}
                else:
                    raise WorkerDenied("Unknown or unapproved worker operation")
            except Exception as exc:
                reply = {"ok": False, "error_type": type(exc).__name__}
            wire.write(json.dumps(reply, separators=(",", ":")) + "\n")
            wire.flush()
        return 0
    except BaseException as exc:
        # Do not print secrets/task content or return a fictitious benchmark score.
        wire.write(json.dumps({
            "ok": False, "error_type": type(exc).__name__,
            "phase": "boot_or_protocol",
        }, separators=(",", ":")) + "\n")
        wire.flush()
        return 2
    finally:
        if env is not None:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    env.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
