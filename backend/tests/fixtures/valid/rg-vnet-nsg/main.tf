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

module "vnet1" {
  source  = "Azure/avm-res-network-virtualnetwork/azurerm"
  version = "0.22.3"

  address_space    = ["10.0.0.0/16"]
  enable_telemetry = false
  location         = "westeurope"
  name             = "vnet-webapp-dev-weu"
  parent_id        = module.rg1.resource_id
}

module "nsg1" {
  source  = "Azure/avm-res-network-networksecuritygroup/azurerm"
  version = "0.6.0"

  enable_telemetry = false
  location         = "westeurope"
  name             = "nsg-webapp-dev-weu"
  parent_id        = module.rg1.resource_id
  security_rules   = { allow_https = { access = "Allow", destination_address_prefix = "*", destination_port_range = "443", direction = "Inbound", name = "allow-https", priority = 100, protocol = "Tcp", source_address_prefix = "Internet", source_port_range = "*" } }
}
