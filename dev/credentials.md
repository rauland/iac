# Credentials for agent sessions

Keep credentials in private files owned by your SSH account, outside project
checkouts. Select the credentials when creating a container. The helper accepts
the credential set you choose; filenames such as `dev.env` do not enforce an
environment boundary. Proxmox ACLs, AWS policies, and the other services' token
permissions must enforce that boundary.

## Supply development tokens

On your trusted workstation, copy [dev.env.example](dev.env.example) to a local
`dev.env` file, replace its placeholders, and remove variables the task does not
need. Use one `KEY=value` per line, without `export` or shell quoting. Values are
literal: `$VAR`, `$(command)`, and quoted strings are not evaluated by a shell.
Multiline values such as SSH private keys belong in separate credential files.

The example covers the variable names used by this repository: Terraform's
Proxmox identity, Ansible's separate inventory identity, AWS state access, and
optional Cloudflare DNS access. Use dev-scoped accounts and tokens. If AWS
credentials are temporary, include `AWS_SESSION_TOKEN` alongside the access key
and secret key. The example does not create or grant any permissions.

Prepare the private directory on the replacement server:

```sh
ssh developer@NEW_SERVER_IP 'install -d -m 700 ~/.config/agent-host'
scp /path/to/private/dev.env developer@NEW_SERVER_IP:.config/agent-host/dev.env
ssh developer@NEW_SERVER_IP 'chmod 600 ~/.config/agent-host/dev.env'
```

On the server:

```sh
codex-container start task-one ~/projects/iac \
  --env-file ~/.config/agent-host/dev.env
codex-container attach task-one
```

The helper checks that the file belongs to your SSH account and is inaccessible
to group and other users. It passes the file to the engine at container creation;
it does not source it, print its contents, edit `.bashrc`, or pass it to image
builds. The variables are available to Codex and commands in the container.
This uses the engine's [environment-file option](https://docs.podman.io/en/latest/markdown/podman-run.1.html#env-file-file).

Environment values are also visible to anyone with access to inspect that
container through its engine. Stopping the container removes its environment;
the original host file remains. To rotate a token, update the host file and
create a new container. Changing the file does not update an existing container.
Files ending in `.env` are ignored by this repository as an additional precaution.

## Supply credential files

For an Ansible SSH private key, create a dedicated directory on the server:

```sh
install -d -m 700 ~/.config/agent-host/dev-files
# Securely copy your dev-only key to dev-files/ansible-ci, then:
chmod 600 ~/.config/agent-host/dev-files/ansible-ci
```

Add this line to your private `dev.env` file:

```text
ANSIBLE_PRIVATE_KEY_FILE=/run/credentials/ansible-ci
```

Start the container with both inputs:

```sh
codex-container start task-one ~/projects/iac \
  --env-file ~/.config/agent-host/dev.env \
  --credentials-dir ~/.config/agent-host/dev-files
```

The directory is mounted read-only at `/run/credentials`. Every file in it is
available to the agent; include only that task's files. Host paths in environment
variables must be replaced with the paths visible inside the container. Verified
SSH host-key pins remain in this repository's `ssh/known_hosts/dev` file. Changing
to an interactive agent environment does not replace host verification.

The image contains the basic tools listed in the container guide. Passing
credentials does not install Terraform, Ansible, or AWS CLI; add required
project tooling to the image before using those credentials.

## Production access

Use development credentials for routine work. For production diagnosis, select
a separate credential set with audit/read permissions limited to the required
resources. Keep production write access in the existing reviewed deployment
workflow, or grant a separate session short-lived, scoped write credentials
when direct intervention is required. This follows the principles of
[least privilege and temporary credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html).

The current repository's Proxmox Terraform **plan** identities also have
`PlanDiskAccess` for disk refresh operations. They are not strictly read-only;
use a suitable audit identity for production inspection. See the
[access configuration](../terraform/platform/access/README.md).

Neither this helper nor these examples impose a production-access policy.
They let you explicitly select credentials; authorization is enforced by the
systems those credentials access.
