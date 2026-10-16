# Storage account rules on the project model (input.resources[].{id, module, inputs}).
package main

storage := "avm-res-storage-storageaccount"

deny contains {"id": "LDO_ST_TLS", "resource": r.id, "msg": sprintf("%s: storage must require TLS 1.2 (min_tls_version is %v)", [r.id, r.inputs.min_tls_version])} if {
	some r in input.resources
	r.module == storage
	r.inputs.min_tls_version != "TLS1_2"
}

warn contains {"id": "LDO_ST_PUBLIC", "resource": r.id, "msg": sprintf("%s: storage is reachable from the public internet (public_network_access_enabled)", [r.id])} if {
	some r in input.resources
	r.module == storage
	r.inputs.public_network_access_enabled == true
}
