# VS Code access

Use Remote - SSH to connect to the replacement Ubuntu host as the same developer
account that owns your rootless containers, then attach Dev Containers to the
running task container. Your editor, terminal, and Codex extension then use the
container's `/workspace` checkout and explicitly supplied credentials.

Install the Remote - SSH and Dev Containers extensions in VS Code on your
workstation. Add the new host to your workstation's SSH configuration:

```sshconfig
Host agent-host
    HostName NEW_SERVER_IP
    User developer
    IdentityFile ~/.ssh/id_ed25519
```

Verify the host key and SSH connection, then use **Remote-SSH: Connect to Host**
and choose `agent-host`. In the SSH window, start a container from its terminal:

```sh
codex-container start task-one ~/projects/iac \
  --env-file ~/.config/agent-host/dev.env
```

Configure the Dev Containers **Docker Path** setting for this remote connection:

```json
{
  "dev.containers.dockerPath": "podman"
}
```

Run **Dev Containers: Attach to Running Container**, choose `codex-task-one`,
and open `/workspace`. Install the Codex extension in that container when VS Code
offers the remote installation target. If needed, complete Codex login from the
container's terminal. Do not install project dependencies on the host merely
to make them available to the container.

If you use Docker instead, keep the normal Docker Path setting and start the
container with `CONTAINER_ENGINE=docker`. The host must already have that engine
available to the developer account; the bootstrap installs rootless Podman.

The underlying workflow is documented by Microsoft for
[Remote - SSH with Dev Containers](https://code.visualstudio.com/remote/advancedcontainers/develop-remote-host).
Microsoft describes Podman 5+ as mostly Docker-CLI-compatible and does not
officially support alternate Docker-compatible CLIs; see its
[Podman guidance](https://code.visualstudio.com/remote/advancedcontainers/docker-options#_podman).
Ubuntu's packaged Podman version may be older. Validate attachment with the
selected host version before migration; an interactive VS Code attachment has
not been tested as part of this change.

Closing VS Code leaves the helper's detached container running. Stop it with
`codex-container stop task-one` when finished. Container-local extension installs,
Codex login, and VS Code server files are disposable along with its home.
