# Proposed private GCS state backend

Status: prepared, not authorized or executed. The active backend remains local.

Create `gs://pillars-514405-terraform-state` in `australia-southeast2`, with uniform
bucket-level access, enforced public-access prevention, object versioning, and
Terraform `prevent_destroy`. The separate root `infra/state-bootstrap` owns the
bucket; the application state never manages its own storage. The only explicit
object grant is for the current human operator. Existing project-level privileged
administrators retain their inherited permissions. GitHub's app deployment identity
and the five runtime identities receive no access to state.

GCS backend locking uses an object in the same bucket; object create/delete access
is required. No retention lock is configured because it would prevent removal of
Terraform lock objects. Version history is retained without an automatic deletion
rule. Stored versions incur GCS storage charges. See the
[HashiCorp GCS backend documentation](https://developer.hashicorp.com/terraform/language/backend/gcs).

Before migration, stop concurrent Terraform operations. Make an ACL-restricted
backup of the original state in `.tools/state-backups/` and verify the SHA-256 hash.
Also preserve the state immediately before activating the backend if later IAM
changes have advanced its serial. These paths are excluded from Git and Docker.

After explicit approval, from the repository root:

```powershell
terraform '-chdir=infra/state-bootstrap' init -input=false
terraform '-chdir=infra/state-bootstrap' plan '-out=state-bucket.tfplan'
# Review: only the new bucket and its object-access grant.
terraform '-chdir=infra/state-bootstrap' apply state-bucket.tfplan
Copy-Item infra/gcp/backend.tf.example infra/gcp/backend.tf
terraform '-chdir=infra/gcp' init -migrate-state '-backend-config=backend.gcs.hcl.example'
# Answer Terraform's migration prompt only under the user's migration approval.
terraform '-chdir=infra/gcp' plan -detailed-exitcode
```

Compare the migrated state's lineage, serial, and resource addresses with the
backup; verify the GCS bucket's versioning, IAM and public-access prevention,
confirm the state object exists, and confirm a refreshed plan has no changes.
Preserve the original snapshots even after verification. Keep the separate
bootstrap root's local state backed up privately as well. Do not use `state push`,
`force-unlock`, or initialize a fresh application state to bypass a migration error.
