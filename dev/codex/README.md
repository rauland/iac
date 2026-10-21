# Disposable Codex development containers

SSH into the development server, then use a named container for each task. The
image includes Codex CLI 0.162.1, Node.js 22, Python, Git, GitHub CLI, ripgrep, and tmux.
The CLI version is pinned; set `CODEX_CONTAINER_VERSION` when building to update it.

## Host setup

Install a container engine once. On this Ubuntu host, Podman can be installed
with:

```sh
sudo apt-get update
sudo apt-get install -y podman uidmap slirp4netns fuse-overlayfs
```

Allow at least 2 GB of free disk space for image builds and project dependencies.
On LXC hosts, the helper detects the environment and uses the
included `podman-lxc.conf` to disable unsupported kernel keyrings, plus Buildah's
`rootless` build isolation mode. These settings apply only to helper commands;
explicit `CONTAINERS_CONF` and `BUILDAH_ISOLATION` settings take precedence.

Prefer a normal SSH account with rootless Podman. It needs subordinate UID and
GID ranges in `/etc/subuid` and `/etc/subgid`; verify them with
`grep "^$(id -un):" /etc/subuid /etc/subgid`. New user accounts normally receive
these ranges automatically. To keep rootless containers running after logout,
an administrator should enable lingering for that account:

```sh
sudo loginctl enable-linger YOUR_SSH_USER
```

Docker also works if already installed and accessible to your SSH account. Set
`CONTAINER_ENGINE=docker` to select it. Use the same account and engine for
building and managing containers. Docker socket access grants control of its
host; this helper never mounts that socket inside a container.

## Connect and work

From your own machine, allocate a terminal for SSH:

```sh
ssh -t YOUR_SSH_USER@agent-host
```

On the development server, from this repository:

```sh
./dev/codex/codex-container build
./dev/codex/codex-container start feature /absolute/path/to/project
./dev/codex/codex-container attach feature
```

Inside the container:

```sh
codex login --device-auth
codex
```

Enable device code login in your ChatGPT account or workspace settings if needed,
then complete the login in your local browser. This is the recommended remote
login flow in the [official OpenAI documentation](https://learn.chatgpt.com/docs/auth#login-on-headless-devices).
Credentials stay in the container's temporary home. Log in once for each new
container; reconnecting to a running container keeps that login.

Detach with **Ctrl-b, then d**. The tmux session and Codex process continue
running if SSH disconnects. Reconnect with the same `attach feature` command.
Exiting the shell ends the tmux session; the container remains until stopped.
Containers do not restart after a host reboot or engine shutdown.

List and dispose of environments from the host:

```sh
./dev/codex/codex-container list
./dev/codex/codex-container stop feature
```

Stopping deletes the container, its login state, shell history, and installed
packages. **Files in `/workspace` persist on the host, including edits and
deletions.** Use a separate clone per task if the checkout should also be
disposable. For Git worktrees, both the worktree and its main Git directory must
be inside the mounted project; a standalone worktree mount cannot resolve a
Git directory elsewhere on the host.

The helper mounts only the selected project, runs as your UID/GID, drops Linux
capabilities, and prevents privilege escalation. Supply credentials explicitly
using `--env-file FILE` and optionally `--credentials-dir DIRECTORY`; see the
[credential setup guide](../credentials.md). Host Codex configuration is not
mounted. Networking uses the engine's normal
outbound network; container ports are not published. Containers share the host
kernel and outbound network access, and can read any credentials in the mounted
project. Keep Codex's normal approval and sandbox settings.

For SELinux hosts, explicitly label a dedicated project directory for container
access before use; the helper does not relabel host files automatically. For
proxy-controlled networks, configure the engine's build and runtime proxy and CA
trust before building. The helper targets local engines on this Linux server,
using their normal local storage; remote Docker contexts are not supported.

## Other commands and updates

```sh
# Run a command without a terminal (also useful for smoke checks).
./dev/codex/codex-container exec feature codex --version

# Build a different CLI version; only newly created containers use the new image.
CODEX_CONTAINER_VERSION=0.162.1 ./dev/codex/codex-container build
```

`CODEX_CONTAINER_IMAGE` overrides the image name, which otherwise includes your
UID and GID. Override images must provide the same tools and writable home for
that identity. Add project dependencies to the Dockerfile for repeatable rebuilds.

Replace `agent-host` with the new server's SSH alias or address. Changing its
hostname also requires updating local DNS/DHCP and SSH host-key mappings.
