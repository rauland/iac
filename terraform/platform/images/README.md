# Shared cloud images

This root publishes cloud images shared by dev and prod workloads. It uses
`proxmox-platform-plan` / `proxmox-platform-apply` GitHub environments and the
scoped `tf-platform-images-plan` / `tf-platform-images-apply` service users.
Image files remain on the configured Proxmox datastore (`local` by default).
Environment-specific Talos boot media stays with its cluster root.

The S3 state key is `terraform/platform/images.tfstate`. Image CI credentials
need access only to this state and its lock file, not `platform/access` state.
The [access guide](../access/README.md) covers credentials and GitHub setup.

Deploy using the Terraform workflow with scope `platform`, mode `single`, target
`images`, or mode `all` for platform. The access root is never included. The
`.disabled` marker works here just as it does for workload roots.

For local initialization, use the existing backend bucket and region:

```sh
terraform -chdir=terraform/platform/images init \
  -backend-config=bucket=YOUR_STATE_BUCKET \
  -backend-config=region=YOUR_AWS_REGION \
  -backend-config=key=terraform/platform/images.tfstate
terraform -chdir=terraform/platform/images plan
```

## Moving an existing prod/images installation

Keep the old initialized `.terraform` directory when moving this root so
Terraform knows the source backend key. Back up the current state and ensure
there are no active image deployments. Then run initialization with
`-migrate-state` and the new key above. Terraform migrates the state while
preserving resource addresses and image ownership. `-reconfigure` alone does
not migrate state.

Record the new backend lineage and verify resource records, outputs, and a
no-change plan before retiring the old `terraform/prod/images.tfstate` current
object. Keep the state backup and
historical S3 versions. Discard saved plans from before the migration and update
image CI state IAM permissions to the new key. Existing Proxmox image files and
VM disks remain in place.
