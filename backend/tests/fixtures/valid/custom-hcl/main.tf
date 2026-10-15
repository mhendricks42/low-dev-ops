terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12"
    }
  }
}

provider "azapi" {}

module "rg1" {
  source  = "Azure/avm-res-resources-resourcegroup/azurerm"
  version = "0.4.0"

  enable_telemetry = false
  location         = "westeurope"
  name             = "rg-webapp-dev-weu"
  tags             = { env = "dev", owner = "platform-team" }
}

# Storage the catalog does not cover yet.
resource "azapi_resource" "sa" {
  type      = "Microsoft.Storage/storageAccounts@2023-05-01"
  name      = "stwebappdevweu"
  parent_id = module.rg1.resource_id
  location  = "westeurope"
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
  }
}

locals {
  # Braces in strings and comments must not confuse the splitter: { } "
  greeting = "hello { world }"
  script   = <<-EOT
    echo "}"
  EOT
}

variable "env" {
  type    = string
  default = "dev"
}

/* Uses var. so the parser must keep it verbatim. */
module "rg2" {
  source  = "Azure/avm-res-resources-resourcegroup/azurerm"
  version = "0.4.0"

  enable_telemetry = false
  location         = "westeurope"
  name             = "rg-webapp-${var.env}-weu"
}
