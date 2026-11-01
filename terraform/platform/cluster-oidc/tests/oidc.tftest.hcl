mock_provider "aws" {}
mock_provider "http" {}

variables {
  state_bucket = "state.example"
}

override_data {
  target = data.terraform_remote_state.cluster["dev"]
  values = {
    outputs = {
      kubernetes_client_configuration = {
        host               = "https://192.0.2.10:6443"
        ca_certificate     = "Y2E="
        client_certificate = "Y2VydA=="
        client_key         = "a2V5"
      }
    }
  }
}
override_data {
  target = data.http.document["dev/.well-known/openid-configuration"]
  values = {
    status_code   = 200
    response_body = "{\"issuer\":\"https://rauland-homelab-oidc.s3.ap-southeast-2.amazonaws.com/dev\",\"jwks_uri\":\"https://rauland-homelab-oidc.s3.ap-southeast-2.amazonaws.com/dev/openid/v1/jwks\"}"
  }
}
override_data {
  target = data.http.document["dev/openid/v1/jwks"]
  values = {
    status_code   = 200
    response_body = "{\"keys\":[]}"
  }
}

run "publishes_only_the_discovery_documents" {
  command = plan

  assert {
    condition     = data.http.document["dev/openid/v1/jwks"].url == "https://192.0.2.10:6443/openid/v1/jwks"
    error_message = "The key set is read from the cluster's API server."
  }
  assert {
    condition     = local.bucket_policy.Statement[0].Resource == ["arn:aws:s3:::rauland-homelab-oidc/dev/.well-known/openid-configuration", "arn:aws:s3:::rauland-homelab-oidc/dev/openid/v1/jwks"]
    error_message = "Only the discovery documents are public."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.oidc.block_public_acls && aws_s3_bucket_public_access_block.oidc.ignore_public_acls
    error_message = "Public ACLs stay blocked; only the bucket policy grants reads."
  }
  assert {
    condition     = aws_iam_openid_connect_provider.cluster["dev"].url == "https://rauland-homelab-oidc.s3.ap-southeast-2.amazonaws.com/dev" && aws_iam_openid_connect_provider.cluster["dev"].client_id_list == toset(["sts.amazonaws.com"])
    error_message = "The provider trusts the published issuer for the STS audience."
  }
}

run "rejects_a_cluster_still_on_its_private_issuer" {
  command = plan

  override_data {
    target = data.http.document["dev/.well-known/openid-configuration"]
    values = {
      status_code   = 200
      response_body = "{\"issuer\":\"https://192.0.2.10:6443\"}"
    }
  }
  expect_failures = [data.http.document]
}
