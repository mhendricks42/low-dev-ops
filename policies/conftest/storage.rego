# Storage account rules on the project model (input.resources[].{id, module, inputs}).
package main

storage := "avm-res-storage-storageaccount"

tls_ok := {"TLS1_2", "TLS1_3"}

# Terraform turns "true" into true, so a string must not slip past a boolean rule.
truthy(v) if v == true

truthy(v) if lower(v) == "true"

deny contains {"id": "LDO_ST_TLS", "resource": r.id, "msg": sprintf("%s: storage must require TLS 1.2 or later (min_tls_version is %v)", [r.id, r.inputs.min_tls_version])} if {
	some r in input.resources
	r.module == storage
	"min_tls_version" in object.keys(r.inputs)
	not r.inputs.min_tls_version in tls_ok
}

warn contains {"id": "LDO_ST_PUBLIC", "resource": r.id, "msg": sprintf("%s: storage is reachable from the public internet (public_network_access_enabled)", [r.id])} if {
	some r in input.resources
	r.module == storage
	truthy(r.inputs.public_network_access_enabled)
}
