# `conftest verify -p policies/conftest` runs these.
package main

st(inputs) := {"resources": [{"id": "st1", "module": "avm-res-storage-storageaccount", "inputs": inputs}]}

test_storage_tls_1_0_denied if {
	some d in deny with input as st({"min_tls_version": "TLS1_0"})
	d.id == "LDO_ST_TLS"
	d.resource == "st1"
}

test_storage_tls_1_2_allowed if {
	count(deny) == 0 with input as st({"min_tls_version": "TLS1_2"})
}

test_storage_public_access_warns if {
	some w in warn with input as st({"min_tls_version": "TLS1_2", "public_network_access_enabled": true})
	w.id == "LDO_ST_PUBLIC"
}

test_storage_private_is_quiet if {
	count(warn) == 0 with input as st({"min_tls_version": "TLS1_2", "public_network_access_enabled": false})
}

test_keyvault_purge_off_denied if {
	some d in deny with input as {"resources": [{"id": "kv1", "module": "avm-res-keyvault-vault", "inputs": {"purge_protection_enabled": false}}]}
	d.id == "LDO_KV_PURGE"
}

nsg(rule) := {"resources": [{"id": "nsg1", "module": "avm-res-network-networksecuritygroup", "inputs": {"security_rules": {"r": rule}}}]}

ssh_from_internet := {"access": "Allow", "direction": "Inbound", "source_address_prefix": "Internet", "destination_port_range": "22"}

test_nsg_ssh_from_internet_denied if {
	some d in deny with input as nsg(ssh_from_internet)
	d.id == "LDO_NSG_ADMIN_OPEN:r"
}

test_nsg_https_from_internet_allowed if {
	count(deny) == 0 with input as nsg(object.union(ssh_from_internet, {"destination_port_range": "443"}))
}

test_nsg_ssh_from_vnet_allowed if {
	count(deny) == 0 with input as nsg(object.union(ssh_from_internet, {"source_address_prefix": "VirtualNetwork"}))
}
