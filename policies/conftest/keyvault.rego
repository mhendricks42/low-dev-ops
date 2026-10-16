# Key Vault rules on the project model.
package main

deny contains {"id": "LDO_KV_PURGE", "resource": r.id, "msg": sprintf("%s: key vault purge protection must stay on", [r.id])} if {
	some r in input.resources
	r.module == "avm-res-keyvault-vault"
	r.inputs.purge_protection_enabled == false
}
