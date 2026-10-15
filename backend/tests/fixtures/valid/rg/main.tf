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
