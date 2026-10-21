# Separate GitHub agent identity

Use a private GitHub App installed only on `rauland/iac`. The app authenticates
as its own bot, independently of the workstation owner's `gh` login. It may
push topic branches and create pull requests; only repository administrators
may merge into the default branch.

## Register and install the app

Open the preconfigured registration form below while signed into your GitHub
account. Review the fields before choosing **Create GitHub App**:

[Register rauland-codex](https://github.com/settings/apps/new?name=rauland-codex&url=https%3A%2F%2Fgithub.com%2Frauland%2Fiac&description=Agent%20identity%20for%20topic%20branches%20and%20pull%20requests&public=false&webhook_active=false&contents=write&pull_requests=write&workflows=write&checks=read&actions=read&metadata=read)

The desired configuration is also recorded in [github-app.json](github-app.json).
The name must be globally unique; choose another name if necessary. Webhooks
should be disabled, no OAuth callback is needed, and installation should be
limited to the account that owns the app. On the app's **Install App** page,
choose **Only select repositories**, then select `rauland/iac`.

| Repository permission | Access | Purpose |
| --- | --- | --- |
| Contents | Read and write | Read code and push topic branches |
| Pull requests | Read and write | Open and update PRs |
| Workflows | Read and write | Include `.github/workflows` changes in a branch |
| Checks | Read | Inspect CI check results |
| Actions | Read | Inspect workflow runs |
| Metadata | Read | Required repository metadata |

Do not grant Administration, Secrets, or Actions write permission, and do not
add the app to any ruleset bypass list. GitHub requires Contents write for
merging as well as branch pushes, so the token permissions alone do not enforce
the requested merge boundary.

## Restrict default-branch merging

Install the separate
[main-merge-authority.json](../.github/policies/main-merge-authority.json)
ruleset alongside the existing `main: pull requests and CI` ruleset. It enables
**Restrict updates** for the default branch and gives only the repository
administrator role (GitHub role ID `5`) a **For pull requests only** bypass.
The GitHub App has no administrator permission and receives no bypass.

The existing PR and CI ruleset remains unchanged and still applies to your
merges. Keeping the two rulesets separate lets you merge passing PRs without
allowing the app to update `main`. The app can still push and update other
branches. This policy protects the default branch; add any other protected
release branches explicitly if the repository gains them.

After reviewing the configuration, the repository owner can install it with:

```sh
gh api --method POST repos/rauland/iac/rulesets \
  --input .github/policies/main-merge-authority.json
```

That command changes live GitHub policy. Committing this file alone does not
enforce it. If a ruleset with that name already exists, update its ID rather
than creating a duplicate. Verify both rulesets are active before issuing a
write-capable app token.

## Issue credentials to the agent

On the app's settings page, generate a private key and retain it on a trusted
host outside the repository and agent containers. Record the App ID and
installation ID. Use the key to obtain a repository-scoped installation access
token, then give only that short-lived token to the agent as `GH_TOKEN`.
Installation tokens normally expire after one hour; the trusted token issuer
must renew them for longer sessions. See
[GitHub's installation-token instructions](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).

Use [the credential file flow](credentials.md) to put `GH_TOKEN` in the private
environment file selected when creating a container. Keep the installation
token out of `.bashrc`, source files, logs, and PR descriptions. The App private
key and the owner's GitHub token must not be included in that environment.

Set Git's HTTPS authentication helper inside that container:

```sh
gh auth setup-git --hostname github.com
git remote set-url origin https://github.com/rauland/iac.git
```

`gh` uses `GH_TOKEN` instead of the owner's cached login. The agent image includes
GitHub CLI. Commit author metadata is separate from API authentication and is not
an access control.

## Verify the boundary

Before publishing agent work, verify:

1. The owner account's credentials are absent from the agent container.
2. The installation token is scoped only to `rauland/iac` with the permissions above.
3. Both default-branch rulesets are active, and the app has no applicable bypass.
4. A topic branch push succeeds and a draft PR is attributed to the app's bot.
5. Merge authority remains with the administrator, including after CI passes.

Do not test merge denial by attempting to merge an actual pending PR: a
misconfiguration could merge it. Verify policy first and use a separate test
repository for destructive permission tests if needed.

App registration, installation, token issuance, and live policy verification
must finish before publishing work as the separate identity. Adding these files
does not create a GitHub App or install a live policy.

References: [registration URL parameters](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters),
[available branch rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
